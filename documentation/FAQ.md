## 常见报错

### 1. 系统找不到指定文件

```
FileNotFoundError: [WinError 2] 系统找不到指定的文件。
```
这个报错是由于 Windows 或者杀毒软件将一些文件识别成了病毒并删除导致的, 请检查 Windows 病毒防护日志, 找到被删除的文件并加入白名单, 重新从项目库拉去对应文件解决问题.

### 2. paddlepaddle 和torch版本冲突

```
OSError:[WinError 127]找不到指定的程序。Error loading "C:\Users25249\Desktop\first\first\lib\site-packages\paddle\...\nvidia\cudnn\bin\cudnn_cnn64 9.dll"or one of its dependencies.
```
这个报错是由于GPU版本的paddle和GPU版本的torch冲突导致的，可以降低paddle的版本来解决问题.

### 3. libiomp5md.dll重复加载

```
0MP:Error #15:Initializing libiomp5md.dllbut found libiomp5md.dll already initialized
OMP: Hint This means that multiple copies of the OpenMp runtime have been linked into the program. That is dangerous, since it can degrade performance or cause incorrect results. The best thing to do is to ensure that only a single 0penMp runtime is linked into the process, e.g. by avoiding static linking of the 0penMp runtime in any library. As anunsafe, unsupported, undocumented workaround you can set the environment variableKMP_DUPLICATE_LIB_OK=TRUE to allow the programto continue to execute, but thatmay cause crashes or silently produce incorrect results, For more information, please see http://www.intel.com/software/products/support/.
```
该问题是torch和paddle重复加载libiomp5md.dll的问题，在Python的依赖中找到重复的libiomp5md.dll选择删除一个可以解决该问题
