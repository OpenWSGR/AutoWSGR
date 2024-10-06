## 常见报错

### 1. 系统找不到指定文件

```
FileNotFoundError: [WinError 2] 系统找不到指定的文件。
```
这个报错是由于 Windows 或者杀毒软件将一些文件识别成了病毒并删除导致的, 请检查 Windows 病毒防护日志, 找到被删除的文件并加入白名单, 重新从项目库拉去对应文件解决问题.

### [paddleocr 后端已经弃用, 请使用 easyocr] 2. paddlepaddle 和torch版本冲突

```
OSError:[WinError 127]找不到指定的程序。Error loading "C:\Users25249\Desktop\first\first\lib\site-packages\paddle\...\nvidia\cudnn\bin\cudnn_cnn64 9.dll"or one of its dependencies.
```
这个报错是由于 GPU 版本的 paddle 和 GPU 版本的 torch 冲突导致的，可以降低 paddle 的版本来解决问题.

### [paddleocr 后端已经弃用, 请使用 easyocr] 3. libiomp5md.dll重复加载

```
0MP:Error #15:Initializing libiomp5md.dllbut found libiomp5md.dll already initialized
OMP: Hint This means that multiple copies of the OpenMp runtime have been linked into the program. That is dangerous, since it can degrade performance or cause incorrect results. The best thing to do is to ensure that only a single 0penMp runtime is linked into the process, e.g. by avoiding static linking of the 0penMp runtime in any library. As anunsafe, unsupported, undocumented workaround you can set the environment variableKMP_DUPLICATE_LIB_OK=TRUE to allow the programto continue to execute, but thatmay cause crashes or silently produce incorrect results, For more information, please see http://www.intel.com/software/products/support/.
```
该问题是torch和paddle重复加载libiomp5md.dll的问题，在Python的依赖中找到重复的libiomp5md.dll选择删除一个可以解决该问题

### 4. 使用 example 中的活动预设文件报错

报错如下：
```
ModuleNotFoundError: No module named autowsgr.fight.event.event_2024_0930
```
报错后面的日期可能不一样，但是都是因为相同的原因导致的。
请检查是否更新依赖，如果没有更新可以使用以下方法更新
```
pip install -U autowsgr
```
或者使用清华源的代理进行更新
```
pip install -U autowsgr -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 5. 使用 pip 更新的时候报错

配置代理或者使用清华源代理进行更新
```
pip install -U autowsgr -i https://pypi.tuna.tsinghua.edu.cn/simple
```
