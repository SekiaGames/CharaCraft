# CharaCraft

用 AI 把一张立绘做成可驱动的 Spine 骨骼动画。

- 流水线：`repro/ws/scripts/`
- 工作台：`repro/studio/`（双击 `run.command`）
- 案例：`Roxy/`

做这个工具之前受到了B站up们的启发：
技能相关参考项目：【【2.0更新】我真的不会美术啊！如何用ai解决素材问题？】 https://www.bilibili.com/video/BV1mXHy6cEWy/?share_source=copy_web&vd_source=0e16539c14edf1afa77eea55972a57af
图生图/图生视频相关的提示词：【零成本！Qwen Image2.1 加 MiniMax H3 制作《无职转生》同人游戏，美术代码全搞定】 https://www.bilibili.com/video/BV1BcaN6fEvC/?share_source=copy_web&vd_source=0e16539c14edf1afa77eea55972a57af

# 关于动作编辑
我现在觉得在这个工具里添加Spine骨骼/动画编辑是一个错误的决定。
    至少也得先选一个开源的2D骨骼系统，能支持Godot引擎的。
相对专业的编辑器来说编辑体验太差，利用不到AI的优势。
目前AI发力的点就是图片生成、视频生成、拆图层。
骨架和动作则需要一个相对固定的模版，用于套用。
可以实现快速出点子快速产出，得到一个通用的能idle/walk/run的模版化角色。
目前不能实现太个性化的商业2D骨骼效果。
    比如Spine官方的demo中的2.5D转头：mix-and-match

# 如何使用本工具
下载本工具：https://github.com/SekiaGames/CharaCraft

下载相关的ComfyUI插件：
    SeeThrough：https://github.com/SekiaGames/ComfyUI-See-through
    comfyui_controlnet_aux：https://github.com/SekiaGames/comfyui_controlnet_aux
ComfyUI插件要放到ComfyUI实例的安装目录下的插件文件夹：ComfyUI/custom_nodes

为什么不直接用原版的ComfyUI插件，要fork一遍？
    因为我用的是Mac，这些ComfyUI对Mac的兼容性不行。
    我做了一些针对本工作流的优化改动。

设置好ComfyUI环境：
    要能正常使用Qwen的文生图、图片编辑，8G显存OK。
    要能正常使用minimaxH3图生视频，8G显存OK。
    要能正常使用SeeThrough工作流拆解动漫角色图层，可能要16G显存，我是用Mac48G共享内存跑的。

准备好环境依赖：setup.command

开启/关闭开机启动：autostart.command

打开前端：run.command

加载示例项目：./Roxy
    Roxy/input目录是所有素材输入，Roxy目录下的其他目录都是生成目录
    前端执行跑一遍，得到的2D骨骼动画文件在Roxy/output目录

# 关于2D骨骼动画的分析
Spine模型浏览器预览工具：SpineAnim/preview.html
SpineAnim目录放了一些案例Spine资源和我的效果分析
对于初学者还是需要先了解一下2D骨骼动画的驱动机制

# 本项目实现自动生成Spine动画的流程
文生图or人物原画+图生图 得到包含人物设定的站姿图
站姿图+图生视频 得到动作视频
站姿图+SeeThrough 得到拆好图层的PSD
用本项目的前端加载一个空的目录作为工作目录（参考Roxy）
    执行跑一遍

在CharaCraft前端界面中的关于动作生成步骤介绍：
1.同步PSD 帮忙复制PSD文件到工作目录用的，自己手动复制也可以。
2.抽帧：将动作视频变成一张张连续的图片
3.DWPose检测生成骨骼关键帧：DWPose工具会分析图片中的肢体关键点，这里直接转换为Spine骨骼
    我创建了一个由17根骨骼构成的简易版的Spine骨架。
    将DWPose中的关键点与Spine骨架结合，实现了输出统一。
    DWPose的连续性太差，误差过大不能直接用于动作，导致最后生成的动作不行。
    后面考虑是不是得手K动作。

# 后续思路（我的笔记）
收集商业Spine效果案例，逐个分析效果实现思路。
保留目前的17根骨骼骨架作为通用骨架，手动K帧实现动作，视频和DWPose仅参考用。
    手K的动作Root是2D空间的原点，脚根重心踩在轴线，不要受到画布宽度干扰。
Qwen图片编辑工作流：生成设计原型
和SeeThrough工作流：生成拆件

# 经验总结（我的笔记）
## SeeThrough工作流
1. 拆件要有完整描边，不能被遮挡。所以期望能补全被遮挡的部分。
2. 某个批次可能会漏掉某个部位，可以尝试3次以内抽卡。侧面视角可能导致双腿被视作联通，拆不开。
3. 可以在工作流留代码里设置不拆特定的部位，或者强调拆哪个部位，不保证有用。
4. 这个模型目前是特定用途的，只能卡通角色。
5. 减少显存占用的选项：group_offload（增加人物耗时）、resolution_depth（降低图层深度排序精度）

## 共享骨架模版
1. 新增角色用部件替代的思路去替换掉模版。基础骨架和动作要能复用。新角色自带延伸骨架和延伸动作。
2. 可以通过缩放模版骨架来实现新增模版（高矮胖瘦版）

## 自动蒙皮
1. 用AI试试
