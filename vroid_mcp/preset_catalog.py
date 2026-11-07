"""Lazy, lab-local offline preset catalog.

Adapted storage/search/annotation ideas from mcjo79/vroid-mcp 0dc7d5e,
mcp_server/preset_cache.py (MIT; licenses/mcjo79-0dc7d5e.txt). No native handles
are retained here. Registry identity is resource plus normalized FULL registered
path; moving/renaming a registered copy creates a new identity. Revision-only
changes preserve annotations. Status describes the latest scan, not sticky news.

Task 8 seam: search/get return copies with fingerprint; publish_image requires
that fingerprint, validated PNG bytes and explicit provenance. resolve_image
revalidates the actual file and returns (metadata, bytes), preferring situation
then native-icon. Situation callers own native/restoration verification.
"""
import asyncio
from contextlib import asynccontextmanager, contextmanager, ExitStack
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import struct
import tempfile
import threading
import time
import zlib
import uuid

from . import catalog_framing as framing

STATUSES = {'new','changed','unchanged','removed','returned','unknown'}
MAX_ROWS = 20000


class _CustomDispatchLease:
    """The worker or the unwinding waiter takes sole ownership of this lock."""
    def __init__(self, resources):
        self.resources = resources
        self.guard = threading.Lock()

    def take(self):
        with self.guard:
            resources, self.resources = self.resources, None
            return resources


_custom_dispatch = ContextVar('vroid_custom_dispatch', default=None)


def bind_custom_selection_export(export):
    """Capture the task-local authorization before scheduling the sync export."""
    lease = _custom_dispatch.get()
    if lease is None:  # The filename API has no catalog selection.
        return export

    def run(operation, payload):
        resources = lease.take()
        if resources is None:
            raise RuntimeError('CUSTOM_ITEM_CATALOG_DISPATCH_EXPIRED')
        with resources:
            return export(operation, payload)
    return run


def _now():
    return datetime.now(timezone.utc).isoformat()


def _text(value, name, maximum=2048, empty=False):
    if (not isinstance(value, str) or len(value) > maximum or '\x00' in value
            or not empty and not value.strip()):
        raise ValueError('INVALID_CATALOG_' + name.upper())
    return value


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def capture_identity(row):
    """Capture inputs exclude independent annotations and model-generation tokens."""
    return {**{k:deepcopy(row.get(k)) for k in ('fingerprint','id','kind','resource','category','revision',
        'custom_revision','group_type','sha256','path','resource_name','selectable_preset_ids','area')},
        'build':row['source']['build']}


def _digest(value):
    return isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) is not None


def _source(value):
    if not isinstance(value,dict) or not _digest(value.get('build')):
        raise ValueError('CATALOG_SOURCE_INVALID')
    _text(value.get('session'),'session',1024)


def _completeness(value):
    return isinstance(value,dict) and set(value)=={'builtin','custom'} and all(type(v) is bool for v in value.values())


def _image_metadata(value, kind):
    if (not isinstance(value,dict) or kind not in ('native-icon','situation') or value.get('kind')!=kind
            or not _digest(value.get('sha256')) or not _digest(value.get('fingerprint'))
            or value.get('path')!='images/'+value['sha256']+'.png'
            or value.get('format')!='png' or not isinstance(value.get('source'),str)
            or kind=='situation' and value.get('verified') is not True
            or any(type(value.get(k)) is not int or not 1<=value[k]<=2048 for k in ('width','height'))
            or type(value.get('bytes')) is not int or not 33<=value['bytes']<=16*1024*1024):
        raise ValueError('CATALOG_IMAGE_METADATA_INVALID')
    if kind=='native-icon' and (value['width']>512 or value['height']>512 or value['bytes']>2*1024*1024):
        raise ValueError('CATALOG_ICON_SIZE_LIMIT')


def _annotation_fields(fields):
    if not isinstance(fields,dict) or set(fields)-{'manual_label','description','tags','colors'}:
        raise ValueError('CATALOG_ANNOTATION_INVALID')
    for name,value in fields.items():
        if name=='manual_label' and value is None: continue
        if name in ('tags','colors'):
            if not isinstance(value,list) or len(value)>100: raise ValueError('CATALOG_ANNOTATION_INVALID')
            for item in value:_text(item,name,100)
        else:_text(value,name,8192,True)


def _json(path, absent):
    try:
        if path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError('CATALOG_SIZE_LIMIT')
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result: raise ValueError('CATALOG_DUPLICATE_JSON_KEY')
                result[key] = value
            return result
        return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('CATALOG_NONFINITE')))
    except FileNotFoundError:
        return deepcopy(absent)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError('CATALOG_CORRUPT') from error


def _row(raw):
    if not isinstance(raw, dict) or raw.get('kind') not in ('builtin','custom'):
        raise ValueError('INVALID_CATALOG_ROW')
    value = deepcopy(raw)
    _text(value.get('resource'), 'resource')
    framing.category(value.get('category'))
    _text(value.get('id'), 'id')
    for key in ('owned','usable','selectable'):
        if not isinstance(value.get(key), bool): raise ValueError('INVALID_CATALOG_' + key.upper())
    if value['kind'] == 'custom':
        _text(value.get('revision'), 'revision')
        _text(value.get('path'), 'path', 4096)
        # Path normalization follows the host filesystem's Windows copy identity.
        registered = os.path.normcase(os.path.abspath(value['path']))
        value['key'] = 'custom:' + value['resource'] + '#' + _hash(registered)
    else:
        value['key'] = value['resource']
    # Opaque model/option IDs and selection state are not content identity.
    fields = ('kind','resource','category','revision','custom_revision','group_type','name',
              'owned','usable','selectable','price_in_coin','is_set_item','sha256','path','resource_name')
    value['fingerprint'] = _hash({k:value[k] for k in fields if k in value})
    return value


def validate_png(data, maximum_side=2048):
    """Bounded RGB/RGBA8 PNG integrity, including CRC and decompressed size."""
    if not isinstance(data, bytes) or not 33 <= len(data) <= 16*1024*1024 or not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('INVALID_CATALOG_PNG')
    offset, header, payload, ended = 8, None, [], False
    while offset < len(data):
        if offset + 12 > len(data): raise ValueError('TRUNCATED_CATALOG_PNG')
        n, kind = struct.unpack('>I',data[offset:offset+4])[0], data[offset+4:offset+8]
        end = offset+8+n
        if end+4 > len(data): raise ValueError('TRUNCATED_CATALOG_PNG')
        value = data[offset+8:end]
        if zlib.crc32(kind+value)&0xffffffff != struct.unpack('>I',data[end:end+4])[0]:
            raise ValueError('CATALOG_PNG_CHECKSUM')
        if kind == b'IHDR':
            if header or offset != 8 or n != 13: raise ValueError('INVALID_CATALOG_PNG_HEADER')
            header = struct.unpack('>IIBBBBB',value)
            w,h,depth,color,compression,filtering,interlace = header
            if (not 1<=w<=maximum_side or not 1<=h<=maximum_side or w*h>4194304
                    or depth!=8 or color not in (2,6) or (compression,filtering,interlace)!=(0,0,0)):
                raise ValueError('UNSUPPORTED_CATALOG_PNG')
        elif kind == b'IDAT': payload.append(value)
        elif kind == b'IEND':
            if n or end+4 != len(data): raise ValueError('INVALID_CATALOG_PNG_END')
            ended = True; break
        elif kind in (b'acTL',b'fcTL',b'fdAT') or not kind[0]&32:
            raise ValueError('UNSUPPORTED_CATALOG_PNG_CHUNK')
        offset = end+4
    if header is None or not ended or not payload: raise ValueError('INCOMPLETE_CATALOG_PNG')
    stride = w*(4 if color==6 else 3)+1
    decoder = zlib.decompressobj()
    try: raw = decoder.decompress(b''.join(payload), stride*h+1)
    except zlib.error as error: raise ValueError('INVALID_CATALOG_PNG_DATA') from error
    if (len(raw)!=stride*h or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail
            or any(raw[i*stride]>4 for i in range(h))): raise ValueError('INVALID_CATALOG_PNG_DATA')
    return dict(width=w,height=h,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),format='png')


class PresetCatalog:
    def __init__(self, root, *, lock_timeout=5):
        self.root = Path(root).resolve()
        self.path = self.root / 'catalog.json'
        self.scratch = self.root.parent / 'temp'
        self.lock_path = self.scratch / ('catalog-' + _hash(os.path.normcase(str(self.root)))[:24] + '.lock')
        if not isinstance(lock_timeout,(int,float)) or not 0 < lock_timeout <= 60:
            raise ValueError('INVALID_CATALOG_LOCK_TIMEOUT')
        self.lock_timeout = lock_timeout

    @contextmanager
    def locked(self, *, wait=True):
        self.scratch.mkdir(parents=True, exist_ok=True)
        # Persistent lock inode; never delete/replace a lock another process holds.
        with self.lock_path.open('a+b') as lock:
            if lock.seek(0,2) == 0: lock.write(b'0'); lock.flush()
            deadline = time.monotonic()+self.lock_timeout
            while True:
                try:
                    lock.seek(0)
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as error:
                    if not wait: raise BlockingIOError('CATALOG_LOCK_BUSY') from error
                    if time.monotonic() >= deadline: raise TimeoutError('CATALOG_LOCK_TIMEOUT')
                    time.sleep(.02)
            try: yield
            finally:
                lock.seek(0)
                if os.name == 'nt': msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else: fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _write(self, path, value):
        if path == self.path:
            self._validate(value)
        data = (json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').replace('\n','\r\n').encode('utf-8')
        if len(data)>32*1024*1024: raise ValueError('CATALOG_SIZE_LIMIT')
        self.root.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='catalog-', suffix='.tmp', dir=self.scratch)
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            os.replace(name,path)
        finally:
            Path(name).unlink(missing_ok=True)

    def _load(self):
        data = _json(self.path, {'schema':1,'presets':{},'source':None,'updated':None})
        return self._validate(data)

    def _validate(self, data):
        if (not isinstance(data,dict) or type(data.get('schema')) is not int or data['schema']!=1
                or not {'schema','source','updated','presets'}<=set(data) or not isinstance(data.get('presets'),dict)
                or len(data['presets'])>MAX_ROWS): raise ValueError('CATALOG_SCHEMA_INVALID')
        def scan(value):
            if not isinstance(value,str) or re.fullmatch('[0-9a-f]{32}',value) is None:
                raise ValueError('CATALOG_SCAN_ID_INVALID')
        if 'scan_id' in data:scan(data['scan_id'])
        if data != {'schema':1,'presets':{},'source':None,'updated':None}:
            _source(data['source']);_text(data['updated'],'updated',100)
            if not _digest(data.get('fingerprint')) or not _completeness(data.get('completeness')):
                raise ValueError('CATALOG_HEADER_INVALID')
        for key, row in data['presets'].items():
            if 'scan_id' in row:scan(row['scan_id'])
            normalized = _row(row)
            if (key != normalized['key'] or row.get('key') != key or row.get('fingerprint') != normalized['fingerprint']
                    or row.get('status') not in STATUSES or not isinstance(row.get('removed'),bool)
                    or not all(isinstance(row.get(f),list) for f in ('tags','colors','annotations','history'))
                    or not isinstance(row.get('images'),dict)):
                raise ValueError('CATALOG_RECORD_INVALID')
            _annotation_fields({k:row.get(k) for k in ('manual_label','description','tags','colors')})
            _source(row.get('source'))
            _text(row.get('label'),'label',8192,True)
            for field in ('first_seen','last_seen'):_text(row.get(field),field,100)
            if len(row['annotations'])>10000 or len(row['history'])>10000:raise ValueError('CATALOG_HISTORY_LIMIT')
            for note in row['annotations']:
                if not isinstance(note,dict):raise ValueError('CATALOG_ANNOTATION_INVALID')
                _text(note.get('author'),'author',200);_text(note.get('time'),'time',100)
                _annotation_fields(note.get('before'));_annotation_fields(note.get('after'))
            for history in row['history']:
                if not isinstance(history,dict) or not _digest(history.get('fingerprint')):
                    raise ValueError('CATALOG_HISTORY_INVALID')
                _text(history.get('last_seen'),'last_seen',100)
            for kind,image in row['images'].items():_image_metadata(image,kind)
        return data

    def get(self, key):
        _text(key,'key',8192)
        data = self._load()
        if key not in data['presets']: raise ValueError('UNKNOWN_CATALOG_KEY')
        return deepcopy(data['presets'][key])

    def current_custom(self, key):
        _text(key, 'key', 8192)
        data = self._load()  # Catalog generations are atomically replaced.
        row = data['presets'].get(key)
        if (not row or row['kind'] != 'custom' or row['removed']
                or row['status'] not in ('new','changed','unchanged','returned')
                or not data.get('scan_id') or row.get('scan_id') != data['scan_id']
                or row['source'] != data['source']
                or not all(row.get(field) is True for field in ('registered','owned','usable','selectable'))
                or not _digest(row.get('sha256'))):
            raise ValueError('CUSTOM_ITEM_CATALOG_SELECTION_STALE_OR_UNUSABLE')
        return row

    @asynccontextmanager
    async def authorize_custom_dispatch(self, observed):
        """Exclude catalog publication from the last comparison through native dispatch."""
        deadline = time.monotonic() + self.lock_timeout
        with ExitStack() as stack:
            while True:
                try:
                    stack.enter_context(self.locked(wait=False))
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline: raise TimeoutError('CATALOG_LOCK_TIMEOUT')
                    await asyncio.sleep(.02)
            current = await asyncio.to_thread(self.current_custom, observed['key'])
            if any(current[k] != observed[k] for k in ('scan_id','fingerprint','source','id')):
                raise ValueError('CUSTOM_ITEM_CATALOG_SELECTION_CHANGED')
            # An asyncio cancellation or timeout can unwind this scope while
            # Frida's synchronous export is still selecting the item in a thread.
            lease = _CustomDispatchLease(stack.pop_all())
            token = _custom_dispatch.set(lease)
            try:
                yield
            finally:
                _custom_dispatch.reset(token)
                unused = lease.take()
                if unused is not None:
                    unused.close()

    def _situation_candidates(self, category):
        """Private complete bounded snapshot; public search remains capped at 200."""
        framing.category(category)
        return deepcopy(sorted((r for r in self._load()['presets'].values()
            if r['category']==category and not r['removed'] and r['owned'] and r['usable'] and r['selectable']),
            key=lambda r:r['key']))

    def _situation_snapshot(self, category, scan_id):
        framing.category(category)
        with self.locked():
            data=self._load()
            if data.get('scan_id')!=scan_id:raise ValueError('CATALOG_SITUATION_SCAN_CHANGED')
            profile=self.get_framing(category)
            rows=sorted((deepcopy(r) for r in data['presets'].values() if r['category']==category
                and not r['removed'] and r['owned'] and r['usable'] and r['selectable']
                and r.get('scan_id')==scan_id and r['source']==data['source']),key=lambda r:r['key'])
            return {'scan_id':scan_id,'source':deepcopy(data['source']),'framing':profile,'rows':rows}

    def _verify_situation_hits(self, observed, hits, raster_cache=None):
        """Linearize skip claims against the same scan and current image inputs."""
        with self.locked():
            data=self._load()
            if (data.get('scan_id')!=observed['scan_id'] or data['source']!=observed['source']
                    or self.get_framing(observed['framing']['category'])!=observed['framing']):
                raise ValueError('CATALOG_CACHE_OBSERVATION_STALE')
            for expected in hits:
                row=data['presets'].get(expected['key'])
                if (not row or row['removed'] or row.get('scan_id')!=observed['scan_id']
                        or capture_identity(row)!=capture_identity(expected)
                        or row['images'].get('situation')!=expected['images'].get('situation')):
                    raise ValueError('CATALOG_CACHE_OBSERVATION_STALE')
                try:current,_=self._resolve_observed_image(row,raster_cache)
                except (ValueError,OSError) as error:
                    raise ValueError('CATALOG_CACHE_OBSERVATION_STALE') from error
                if current!=expected['images']['situation']:
                    raise ValueError('CATALOG_CACHE_OBSERVATION_STALE')
            return len(hits)

    def sync(self, rows, source, complete):
        if (not isinstance(rows,list) or len(rows)>MAX_ROWS or not isinstance(source,dict)
                or not _completeness(complete)):
            raise ValueError('INVALID_CATALOG_SCAN')
        _source(source)
        observed,ids = {},set()
        for raw in rows:
            row = _row(raw)
            if row['key'] in observed: raise ValueError('CATALOG_DUPLICATE_RESOURCE')
            if row['kind']=='builtin':
                if row['id'] in ids:raise ValueError('CATALOG_DUPLICATE_NATIVE_ID')
                ids.add(row['id'])
            observed[row['key']] = row
        now = _now();scan_id=uuid.uuid4().hex
        with self.locked():
            data = self._load()
            for key, row in observed.items():
                previous = data['presets'].get(key)
                if previous:
                    status = 'returned' if previous['removed'] else ('changed' if previous['fingerprint']!=row['fingerprint'] else 'unchanged')
                    preserved = {k:deepcopy(previous[k]) for k in ('first_seen','manual_label','description','tags','colors','annotations','history','images')}
                    if previous['fingerprint']!=row['fingerprint']:
                        preserved['history'].append({k:deepcopy(previous.get(k)) for k in ('revision','name','fingerprint','last_seen')})
                        preserved['images'] = {}
                    row.update(preserved)
                else:
                    status = 'new'
                    row.update(first_seen=now,manual_label=None,description='',tags=[],colors=[],annotations=[],history=[],images={})
                row.update(status=status,removed=False,removed_since=None,last_seen=now,source=deepcopy(source),scan_id=scan_id)
                row['label'] = row['manual_label'] or row.get('name') or row['resource']
                data['presets'][key] = row
            for key, row in data['presets'].items():
                if key in observed: continue
                if complete[row['kind']]:
                    row.update(status='removed',removed=True,removed_since=row.get('removed_since') or now)
                elif not row['removed']:
                    row['status'] = 'unknown'
            data.update(source=deepcopy(source),updated=now,completeness=complete,scan_id=scan_id,
                        fingerprint=_hash(sorted((key,row['fingerprint']) for key,row in observed.items())))
            if len(data['presets'])>MAX_ROWS: raise ValueError('CATALOG_ROW_LIMIT')
            self._write(self.path,data)
        return {'observed':len(observed),'complete':complete,'fingerprint':data['fingerprint'], 'source':source,'scan_id':scan_id}

    def search(self, query='', category=None, kind=None, annotated_only=False, include_locked=False,
               status=None, include_removed=False, limit=50, owned=None):
        _text(query,'query',1024,True)
        if category is not None: framing.category(category)
        if kind is not None and kind not in ('builtin','custom'): raise ValueError('INVALID_CATALOG_KIND')
        if status is not None and status not in STATUSES: raise ValueError('INVALID_CATALOG_STATUS')
        if type(limit) is not int or not 1<=limit<=200: raise ValueError('INVALID_CATALOG_LIMIT')
        if any(type(v) is not bool for v in (annotated_only,include_locked,include_removed)):
            raise ValueError('INVALID_CATALOG_FILTER')
        if owned is not None and type(owned) is not bool:
            raise ValueError('INVALID_CATALOG_OWNED_FILTER')
        words, result = query.casefold().split(), []
        for row in sorted(self._load()['presets'].values(),key=lambda r:r['key']):
            if (category is not None and row['category']!=category or kind is not None and row['kind']!=kind
                    or status is not None and row['status']!=status or not include_removed and row['removed']
                    or owned is not None and row['owned'] is not owned
                    or not include_locked and not row['usable'] or annotated_only and not row['annotations']): continue
            haystack = ' '.join(str(row.get(k,'')) for k in ('label','description','tags','colors','category','name','kind','resource')).casefold()
            if all(w in haystack for w in words): result.append(deepcopy(row))
            if len(result)==limit: break
        return result

    def annotate(self, key, author, label=None, description=None, tags=None, colors=None, replace=False):
        _text(author,'author',200)
        if type(replace) is not bool: raise ValueError('INVALID_CATALOG_REPLACE')
        fields = {}
        for name,value in (('manual_label',label),('description',description)):
            if value is not None: fields[name] = _text(value,name,8192,True)
        for name,value in (('tags',tags),('colors',colors)):
            if value is not None:
                if not isinstance(value,list) or len(value)>100: raise ValueError('INVALID_CATALOG_' + name.upper())
                fields[name] = list(dict.fromkeys(_text(v,name,100).strip().lower() for v in value))
        with self.locked():
            data = self._load()
            if key not in data['presets']: raise ValueError('UNKNOWN_CATALOG_KEY')
            row = data['presets'][key]; before = {k:deepcopy(row[k]) for k in fields}
            for name,value in fields.items():
                row[name] = value if replace or name not in ('tags','colors') else list(dict.fromkeys(row[name]+value))
            row['annotations'].append(dict(author=author,time=_now(),before=before,after={k:deepcopy(row[k]) for k in fields}))
            if len(row['annotations'])>10000:raise ValueError('CATALOG_HISTORY_LIMIT')
            row['label'] = row['manual_label'] or row.get('name') or row['resource']
            self._write(self.path,data)
            return deepcopy(row)

    def _overrides(self):
        value = _json(self.root/'framing_overrides.json', {'schema':1,'overrides':{}})
        if (not isinstance(value,dict) or type(value.get('schema')) is not int or value['schema']!=1
                or not isinstance(value.get('overrides'),dict)):
            raise ValueError('FRAMING_SCHEMA_INVALID')
        for key,profile in value['overrides'].items(): framing.category(key); framing.validate(profile)
        return value

    def get_framing(self, category=None):
        overrides = self._overrides()['overrides']
        if category is None:
            return {key:framing.resolve(key,overrides) for key in sorted(set(framing.defaults()) | set(overrides))}
        return framing.resolve(category,overrides)

    def set_framing(self, category, **fields):
        framing.category(category)
        # Validate before creating scratch/root, then validate again under lock.
        base = {k:self.get_framing(category)[k] for k in framing.profile()}
        framing.validate({**base,**fields})
        with self.locked():
            data = self._overrides()
            base = {k:framing.resolve(category,data['overrides'])[k] for k in framing.profile()}
            data['overrides'][category] = framing.validate({**base,**fields})
            self._write(self.root/'framing_overrides.json',data)
        return self.get_framing(category)

    def reset_framing(self, category=None):
        if category is not None: framing.category(category)
        with self.locked():
            data = self._overrides()
            if category is None: data['overrides'].clear()
            else: data['overrides'].pop(category,None)
            self._write(self.root/'framing_overrides.json',data)
        return self.get_framing(category)

    def publish_image(self, key, data, provenance, expected_fingerprint, *, expected_situation=None):
        if (not isinstance(provenance,dict) or provenance.get('kind') not in ('native-icon','situation')
                or not isinstance(provenance.get('source'),str)
                or provenance['kind']=='situation' and provenance.get('verified') is not True):
            raise ValueError('INVALID_CATALOG_IMAGE_PROVENANCE')
        kind = provenance['kind']
        info = validate_png(data,512 if kind=='native-icon' else 2048)
        if kind=='native-icon' and len(data)>2*1024*1024: raise ValueError('CATALOG_ICON_SIZE_LIMIT')
        with self.locked():
            catalog = self._load()
            row = catalog['presets'].get(key)
            if not row or row['fingerprint'] != expected_fingerprint or row['removed']:
                raise ValueError('CATALOG_IMAGE_IDENTITY_STALE')
            if expected_situation is not None:
                if (kind!='situation' or catalog.get('scan_id')!=expected_situation['scan_id']
                        or row.get('scan_id')!=expected_situation['scan_id']
                        or capture_identity(row)!=expected_situation['identity']
                        or self.get_framing(row['category'])!=expected_situation['framing']
                        or provenance.get('capture_input')!=expected_situation['identity']
                        or provenance.get('requested_framing')!=expected_situation['framing']):
                    raise ValueError('CATALOG_IMAGE_CAPTURE_INPUT_STALE')
            relative = 'images/' + info['sha256'] + '.png'
            folder = self.root/'images'
            folder.mkdir(parents=True,exist_ok=True)
            if not folder.resolve().is_relative_to(self.root): raise ValueError('CATALOG_IMAGE_PATH_ESCAPE')
            destination = self.root/relative
            if destination.exists():
                if destination.is_symlink() or destination.read_bytes()!=data: raise ValueError('CATALOG_IMAGE_CONFLICT')
            else:
                # Stage complete bytes on the same volume, then publish without
                # replacing existing evidence. A hard link is atomic/no-overwrite.
                fd,name=tempfile.mkstemp(prefix='catalog-image-',suffix='.tmp',dir=self.scratch)
                try:
                    with os.fdopen(fd,'wb') as stream:
                        stream.write(data); stream.flush(); os.fsync(stream.fileno())
                    os.link(name,destination)
                finally:
                    Path(name).unlink(missing_ok=True)
            metadata = {**deepcopy(provenance),**info,'path':relative,'time':_now(),'fingerprint':expected_fingerprint}
            row['images'][kind] = metadata
            self._write(self.path,catalog)
            return deepcopy(metadata)

    def resolve_image(self, key):
        _text(key,'key',8192)
        # Catalog, row and effective framing form one current observation.
        # A missing scan retains old row identities and bytes for inspection;
        # those identities alone cannot promote a historical situation preview.
        with self.locked():
            data=self._load()
            if key not in data['presets']:raise ValueError('UNKNOWN_CATALOG_KEY')
            row=data['presets'][key]
            if (row['removed'] or row['status'] not in ('new','changed','unchanged','returned')
                    or data.get('scan_id') is None or row.get('scan_id')!=data['scan_id']
                    or row['source']!=data['source']):
                # Filter only this read's local view; persist no history changes.
                row['images'].pop('situation',None)
            return self._resolve_observed_image(row)

    def _resolve_observed_image(self, row, raster_cache=None):
        """Validate a bounded frozen row's blob without decoding the catalog again."""
        for kind in ('situation','native-icon'):
            image = row['images'].get(kind)
            if image is None: continue
            if kind=='situation' and (
                    image.get('capture_input')!=capture_identity(row)
                    or image.get('requested_framing')!=self.get_framing(row['category'])):
                continue
            _image_metadata(image,kind)
            if not isinstance(image,dict) or image.get('kind')!=kind or image.get('fingerprint')!=row['fingerprint']:
                raise ValueError('CATALOG_IMAGE_METADATA_INVALID')
            relative = image.get('path')
            if (not isinstance(relative,str) or '\\' in relative or ':' in relative
                    or PurePosixPath(relative).is_absolute() or '..' in PurePosixPath(relative).parts
                    or not relative.startswith('images/')): raise ValueError('CATALOG_IMAGE_PATH_ESCAPE')
            path = self.root/relative
            if not path.resolve().is_relative_to(self.root): raise ValueError('CATALOG_IMAGE_PATH_ESCAPE')
            try:
                if path.stat().st_size>16*1024*1024: raise ValueError('CATALOG_IMAGE_SIZE_LIMIT')
                data = path.read_bytes()
            except FileNotFoundError: continue
            actual = validate_png(data,512 if kind=='native-icon' else 2048)
            if any(image.get(k)!=v for k,v in actual.items()): raise ValueError('CATALOG_IMAGE_BYTES_CHANGED')
            if kind=='situation':
                # Legacy/incomplete receipts remain inspectable in get(). They
                # are historical evidence, never a current verified preview.
                from .situation_proof import capture_proof,definition,raster_evidence
                from .capture_quality import decode_capture
                import base64
                try:
                    if (image.get('source')!='clean_fixed_camera_render' or image.get('build')!=row['source']['build']
                            or image.get('verified') is not True):continue
                    decode_capture({**image,'base64':base64.b64encode(data).decode('ascii')},512,'balanced')
                    capture_proof(image.get('framing'),image['requested_framing'])
                    native=definition(image.get('membership'))
                    # Serialized equality preserves the distinction between JSON false and 0.
                    if _hash(image.get('native_definition'))!=_hash(native):continue
                    tested=image.get('tested');root=native['root']
                    if (not isinstance(tested,dict) or tested.get('resource')!=row['resource'] or tested.get('kind')!=row['kind']
                            or any(tested.get(k)!=root[k] for k in ('id','type','revision'))
                            or tested.get('group_resource')!=root['resource_name']
                            or row['kind']=='custom' and any(tested.get(k)!=row.get(k) for k in ('custom_revision','sha256'))):continue
                    if raster_cache is None:raster_cache={}
                    if actual['sha256'] not in raster_cache:raster_cache[actual['sha256']]=raster_evidence(data)
                    if image.get('raster')!=raster_cache[actual['sha256']]:continue
                except (ValueError,KeyError,TypeError):continue
            return deepcopy(image),data
        raise ValueError('CATALOG_IMAGE_UNAVAILABLE')
