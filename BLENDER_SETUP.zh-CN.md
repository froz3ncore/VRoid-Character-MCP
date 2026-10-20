# Blender、VRM 与 XWear：外部服装接入指南

本指南补充从 Tripo／其他建模工具到 VRoid 换装之间的准备步骤。只使用 MCP 调整脸型、发型、妆容，或导入已经制作好的 `.xwear` 时，不需要安装下面全部工具。

## 先区分三个插件

| 工具 | 安装在哪里 | 在流程中负责什么 |
|---|---|---|
| **VRM format / VRM Add-on for Blender**，第三方项目 | Blender | 导入／导出 VRM，编辑 Humanoid 骨骼映射、MToon 与 VRM SpringBone 数据，提供身体和骨架参考 |
| **VRoid MCP — Direct XWear (Experimental)**，本仓库提供 | Blender | 将已经绑定的服装网格与骨架导出为受限的 XWear v2 包；菜单为 `File → Export → Direct XWear — Experimental (.xwear)` |
| **XWear Packager**，pixiv 官方 | Unity，经 VCC 安装 | 官方的服装 XWear 转换路线；和本仓库的 Blender 直出器是两条可选路线 |

MCP 服务运行在 Python／VRoid 副本侧；这两个 Blender 插件需要安装到实际执行建模或后台脚本的 Blender 环境，`pip install -r requirements.txt` 不会安装它们。

## 1. 安装 Blender VRM 插件

第三方项目：[VRM Add-on for Blender](https://github.com/saturday06/VRM-Addon-for-Blender)，安装步骤以其[官方安装说明](https://vrm-addon-for-blender.info/en-us/installation/)为准。

对于 Blender 4.2 及以上版本，可在 `Edit → Preferences → Get Extensions` 搜索 **VRM format** 并安装；也可以从 [Blender Extensions](https://extensions.blender.org/add-ons/vrm/) 下载适配版本的 ZIP，再用 `Add-ons → Install from Disk` 安装。确认插件已启用；下载 ZIP 不要先解压。

安装后先检查：

1. `File → Import` 中能找到 VRM 导入入口。
2. 导入自己的底模 `.vrm`，确认身体和骨架完整，并检查 Humanoid 映射。
3. 如需导出弹簧骨，确认骨架上存在 VRM 1.0 SpringBone 配置，关节与碰撞体引用有效。

本仓库直出器的 `bl_info` 声明最低 Blender 4.2；这不是所有较新版本都经过完整验收的保证。请为你的 Blender 版本选择兼容的 VRM 扩展，并先用小样本验证。本机开发环境中可见 Blender 5.0／VRM 4.5.0 与 Blender 5.2／VRM 4.7.2 的安装记录，不要求安装最新版本，也不代表这两组都完成了同等测试。

**这个 VRM 插件不负责生成 `.xwear`。** 它提供底模、骨骼、材质和弹簧数据的编辑能力，不会自动让 Tripo 网格获得正确蒙皮或衣物碰撞。

## 2. 安装本仓库的 Direct XWear 插件

当前源码版本为 **0.2.0**，位置为 [`pipeline/blender-addons/vroid_xwear_direct/`](pipeline/blender-addons/vroid_xwear_direct/)。这是实验性的 Blender 直出器，不是 pixiv 官方 XWear Packager。

从当前克隆中的源码打包，避免使用过期 ZIP。在仓库根目录的 PowerShell 中执行：

```powershell
$xwearZip = Join-Path $env:TEMP "vroid_xwear_direct-0.2.0.zip"
Compress-Archive `
  -LiteralPath .\pipeline\blender-addons\vroid_xwear_direct `
  -DestinationPath $xwearZip
$xwearZip
```

如果目标 ZIP 已存在，请换一个新路径，不必覆盖旧包。ZIP 顶层应直接包含 `vroid_xwear_direct/`，其下有 `__init__.py`，不要再额外包一层仓库目录。

在 Blender 中打开 `Edit → Preferences → Add-ons → Install from Disk`，选择该 ZIP，启用 **VRoid MCP — Direct XWear (Experimental)**。随后在 `File → Export` 中确认出现 **Direct XWear — Experimental (.xwear)**。

目录中的 `fit.py`、`sleeve_gather.py`、`skirt_contact.py` 是针对显式配置的开发辅助模块，不代表安装后自动完成身体适配、袖口修复或裙摆碰撞；后裙碰撞任务仍暂停。

## 3. 从 Tripo／外部模型到 VRoid

```text
角色设计参考 → Tripo／其他工具生成素材 → Blender 导入网格
                                              ↓
VRoid 底模 → 导出参考 VRM → VRM 插件导入身体与骨架
                                              ↓
                       拆件、缩放对位、修网格、绑定与权重检查
                                              ↓
                           Direct XWear 导出衣物 .xwear
                                              ↓
                    VRoid 换装 → 保存 .xroid → 导出成品 .vrm
```

### 准备身体与服装

1. 在 VRoid 中准备角色底模；需要妆容时，先在普通编辑模式完成并另存 `.vroid`。
2. 从 VRoid 原生功能导出用于对位的参考 `.vrm`。Blender VRM 插件读取的是 `.vrm`，不能把 `.vroid` 当 VRM 直接导入。
3. 在 Blender 导入参考 VRM 与外部服装网格，保留原模型副本，核对正面方向、比例、身体位置与静止姿态。
4. 整理衣饰部件、UV 和材质，处理不需要的身体碎片，修正衣物贴合。
5. 将衣物绑定到目标骨架并检查权重；Tripo 自动绑定不能直接视为已经匹配 VRoid 骨架。

### 导出前检查

- 选择 **一个 Armature 和要导出的服装 Mesh**，不要把用于参考的裸身体网格一起选进去。
- 骨架回到静止姿态，不要把行走／坐姿或弹簧模拟结果当作绑定姿态导出。
- 保留有效、唯一的 Humanoid 映射。导入 VRM 的骨架可通过 VRM 插件提供映射；没有映射扩展时，直出器只会回退匹配少量标准英文骨名，不能靠随意改名代替正确映射。
- 每个导出 Mesh 要有 UV，且仅有一个可见的 Armature 修改器并指向所选骨架；其他修改器应先在工作副本中处理。
- 每个顶点要有 **1～4 个有效骨骼权重**。不能靠导出自动解决无权重或过多骨骼影响。
- 不支持实际 morph／Shape Key 导出；仅有 Basis 不等于存在可导出的表情形变。
- 材质使用支持的不透明纯色或简单 Principled BSDF，底色可直接连接一张已保存的 sRGB 图片。复杂节点需先在副本中整理或烘焙成支持的底色；VRM 插件导入的 MToon 节点组不能直接当作受支持的 Principled 材质输出。
- 如导出 VRM 1.0 弹簧骨，使用单位骨架缩放，检查 joint、collider group 与球／胶囊碰撞体引用。导出配置不等于完成布料求解。

### 执行导出

打开 `File → Export → Direct XWear — Experimental (.xwear)`，填写物品名和作者，并选择一个不存在的新文件名。

`Character front` 要与实际模型朝向一致：普通 Blender 朝前约定可选 `-Y`；本项目从原生采集参考生成的部分场景朝 `+X`，应选 `+X (captured VRoid reference)`。不要为了消除画面偏位而盲目更改绑定姿态。

当前 0.2.0 支持静止绑定、UV0、不透明底色／直接底色图片，以及受限 VRM 1 弹簧数据。它不导出动画、morph、完整 PBR／法线／发光贴图或透明材质，也不是任意 Blender 场景的通用转换器。

### 在 VRoid 中验收

通过 MCP 调用 `get_wear_status`，取得新的 wear token，按工具参数打开装配并 `import_xwear`。保持预览停止，检查贴合与正／侧／背视图；再保存新的 `.xroid`，重新打开检查，最后导出新的 `.vrm`。

导出成功后仍要检查真实原生导入、材质、蒙皮与动作。`tools/vrm_inspect.py` 可以检查最终 VRM 的部分结构，但不能替代外观、碰撞和目标引擎验证。

普通编辑画板用于 VRoid 底模及其原生部位。装配里的外部 XWear 网格不会因此变成可随意重塑的原生衣服；外部衣物的网格和复杂材质仍需回 Blender 修改后重新导出／导入。

## 4. 可选的官方 Unity 路线

如果选择官方 XWear 转换方式，参照 pixiv 的 [XWear Packager 安装说明](https://vroid.pixiv.help/hc/en-us/articles/38903414455449-How-to-install-the-XWear-Packager)及[衣饰转换说明](https://vroid.pixiv.help/hc/en-us/articles/38730429718041)。它是 Unity 编辑器扩展，按照官方要求经 VRChat Creator Companion（VCC）添加和安装，并非 Blender 插件。

两条路线都以可用的 `.xwear` 交给 VRoid 换装。已经有可导入的 XWear 时，无需为了 MCP 再安装官方 Unity 插件；本仓库直出流程也不要求 Unity。VRoid 换装本身和本 MCP 的操作入口仍在 VRoid Studio 中。

## 文件格式速查

| 格式 | 用途 |
|---|---|
| `.vroid` | VRoid 普通编辑源文件；不能直接由 Blender VRM 插件导入 |
| `.blend` | Blender 可编辑网格、骨架、材质等源文件 |
| `.glb` / `.fbx` | 常见外部素材交换格式；本身不等于可直接穿戴的 XWear |
| `.xwear` | 可导入 VRoid 换装的衣饰包 |
| `.xroid` | VRoid 换装装配编辑文件，供保存和继续调整 |
| `.vrm` | 角色交换与下游使用；导入引擎时继续验证材质、骨架和物理 |

## 常见问题

| 问题 | 先检查 |
|---|---|
| 找不到 Direct XWear 导出菜单 | 是否在正确的 Blender 环境启用插件，ZIP 是否包含正确顶层目录 |
| 找不到 VRM 导入菜单或映射面板 | 是否安装并启用第三方 **VRM format**；它与 Direct XWear 是不同插件 |
| `A Hips humanoid assignment is required` | VRM Humanoid 映射是否有效；骨架是否只是原始 Tripo 自动骨架 |
| `Apply non-armature modifiers first` | 导出 Mesh 是否还有其他可见修改器，Armature 是否指向所选骨架 |
| `Need 1..4 positive bone influences per vertex` | 是否存在无权重顶点或超过四个有效骨骼影响 |
| `Only direct Principled materials supported` | 是否仍在使用 MToon 节点组或其他自定义着色器；需要整理为支持的材质 |
| 衣服原生导入后偏位或动作异常 | 参考底模、朝向、比例、静止绑定与权重；不能只看静态包围盒 |

[返回简体中文 README](README.zh-CN.md)
