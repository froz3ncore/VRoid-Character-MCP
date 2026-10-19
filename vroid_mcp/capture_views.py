"""Portable regional view names; filenames never contain Windows stream separators."""
REGIONS=('body','face','head','upper','legs','feet')
ANGLES=('front','back','left','right','three_quarter_left','three_quarter_right')
REGIONAL_VIEWS=tuple(f'{r}_{a}' for r in REGIONS for a in ANGLES)
LEGACY_MODEL_VIEWS=('front','side','back','three_quarter','full_front','full_side','full_back','full_three_quarter')
LEGACY_WEAR_VIEWS=('front','side','back','three_quarter')
CAPTURE_VIEWS=LEGACY_MODEL_VIEWS+REGIONAL_VIEWS+('photo',)
WEAR_CAPTURE_VIEWS=LEGACY_WEAR_VIEWS+REGIONAL_VIEWS

def is_regional(view: str) -> bool:
    return view in REGIONAL_VIEWS

def validate_wear_views(views: list[str],maximum: int=6) -> None:
    if (not views or len(views)>maximum or len(set(views))!=len(views)
        or any(v not in WEAR_CAPTURE_VIEWS for v in views)):
        raise ValueError(f'Choose 1-{maximum} distinct supported Dress-up views')

def review_reference(current: dict, baseline: dict | None) -> tuple[dict,str]:
    old=(baseline or {}).get('framing_reference')
    if (old and old.get('model_token')==current['model_token']
        and old.get('root_id')==current['root_id']):
        return {**current,'bounds':old['bounds'],'reference_frame':old['reference_frame']},'baseline_locked'
    return current,'current_model'
