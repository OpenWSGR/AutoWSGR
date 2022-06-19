## 简单介绍

### 环境和语言

- python:`3.7.4-64bit`
- c++:`c++17`

- system:`win10-64`

### 功能

提供 `WSGR` 游戏级别接口以及部分图像和原子操作接口。

### 默认设置

- 进入任何战斗前都将会修理队伍中中破或大破的舰船

### 结构

```
./source
	./python_src:python 源码
		./api:图像处理函数和与模拟器，计算机交互的接口
		./constants:常量
		./fight:战斗相关接口
		./game:其它游戏接口
		./save_load:初始化和持久化
		./support:程序记录器和一些必须数据结构的实现,日志功能
		main.py:主入口
	./c_src:C 源码
./data
	./images:图像文件
	./tunnel:多语言通信通道
	./log:日志文件
	./tmp:临时文件
	./settings:设置文件
	
./release: 发行版

```



### 主要接口

注1:timer 为记录器,存储一些全局信息

注2:所有主要接口均在 main.py  中暴露，请善于使用代码补全功能和定义跳转功能

```python
def normal_fight(timer:Timer, chapter, node, team, decision_maker:DecisionBlock=None, repair:RepairBlock=None, *args, **kwargs):

    """进行常规地图战斗
    Args:
        timer (Timer): _description_
        chapter (int): 章节
        node (int): 节点
        team (int): 1~4 的整数
        decision_maker (DecisionBlock): 决策模块. Defaults to None.
        repair (RepairBlock, optional): 修理模块. Defaults to None.
        kwargs: 一些其它参数
    Returns:
        'dock is full':船坞已满
        'SL': 进行了 SL 操作
    """

def GainBounds(timer:Timer):
    """检查任务情况,如果可以领取奖励则领取

    Args:
        timer (Timer): _description_
    """
    
def ChangeShips(timer:Timer, team, list):
    """更换编队舰船

    Args:
        team (int): 1~4,表示舰队编号
        list (舰船名称列表): 
    
    For instance:
        ChangeShips(timer, 2, [None, "萤火虫", "伏尔塔", "吹雪", "明斯克", None, None])

    """

def start_script():
    """启动脚本,返回一个 Timer 记录器

    Returns:
        Timer: 该模拟器的记录器
    """

@logit_time()        
def expedition(timer:Timer, try_times=0):
    """检查远征,如果有未收获远征,则全部收获并用原队伍继续

    Args:
        timer (Timer): _description_
    """

def RepairByBath(timer:Timer):
    """使用浴室修理修理时间最长的单位

    Args:
        timer (Timer): _description_
    """

def battle(timer:Timer, node, times, decision_maker:DecisionBlock=None, repair_logic:RepairBlock=None, team=None, try_times=0, *args, **kwargs):
    """进行战役

    Args:
        node (int): 战役的节点,从简单(1~5)到困难(6~10),内部顺序为 驱逐,巡洋,战列...
        times (int): 次数
        decision_maker (DecisionBlock, optional): 决策模块. Defaults to None.
        team (_type_, optional): 暂时不管. Defaults to None.
    
    """

def normal_exercise(timer:Timer, team, decision_maker:DecisionBlock=None, refresh_times=0, *args, **kwargs):
    """常规演习:挑战所有可以挑战的

    Args:
        timer (Timer): _description_
        team (int): 用哪个队伍打
        
    """

def friend_exercise(timer:Timer, team, decision_maker:DecisionBlock=None, targets=[1, 2, 3], uids=None, *args, **kwargs):
    """好友演习
    目前只支持选前四个演习
    Todo:
        自动获取并识别好友,uid 识别
    Args:
        timer (Timer): _description_
        team (int): 队伍编号
        times (int): 每一个好友打几次
        targets (list): 打哪些好友,如果缺省则前三个. Defaults to [1,2,3]
        ships (_type_, optional): 不管. Defaults to None.
    """


```



### 战斗决策模块

```python
class DecisionBlock():
    def __init__(self, *args, **kwargs):
        self.dict=kwargs
    def make_decision(self, timer:Timer, type, *args, **kwargs):
        """通过 timer 的信息进行决策

        Args:
            type (str): 决策类型
                values:
                    'formation': 阵型返回 0~6 的整数,0 为撤退, 6 为迂回, 其它依次为单纵,复纵...
                    'night': 是否进行夜战返回 0/1
                    'fight_condition': 选择战况,返回 1~5, 左上为 1, 中间为 2, 右上为 3, 左下为 4
                    'continue:' 回港或继续, 回港为 0, 继续为 1
        Returns:
            int: 描述决策
        """
```



### 记录器

```python
class Timer():
    """程序运行记录器,用于记录和传递部分数据,同时用于区分多开
    
    
    """
    def __init__(self):
        """Todo
        参考银河远征的战斗模拟写一个 Ship 类,更好的保存信息
        """
        self.start_time = time.time()
        self.log_filepre = get_time_as_string()
        self.screen = None
        self.resolution = (960,540)
        self.ship_position = (0,0)
        self.ship_point = "A"  #常规地图战斗中,当前战斗点位的编号
        self.chapter = 1  #章节名,战役为 'battle', 演习为 'exercise'
        self.node = 1	#节点名
        self.ship_status = [0, 0, 0, 0, 0, 0, 0] #我方舰船状态
        self.enemy_type_count = {}  #字典,每种敌人舰船分别有多少个
        self.now_page = None  #当前所在节点名
        self.ui = None  #ui 树
        self.device_name = 'emulator-5554' #设备名,雷电模拟器默认值
        self.expedition_status = None  #远征状态记录器
        self.team = 1  #当前队伍名
        self.defaul_decision_maker = None  #默认决策模块
        self.ammo = 10
        self.oil = 10
        """
        以上时能用到的
        以下是暂时用不到的
        """
        
        self.friends = []
        self.enemies = []
        self.enemy_ship_type = [None, NO, NO, NO, NO, NO, NO]
        self.friend_ship_type = [None, NO, NO, NO, NO, NO, NO]
        self.defaul_repair_logic = None
        self.fight_result = None
        self.last_mission_compelted = 0
        self.last_expedition_checktime = time.time()


        
```

### 一些参数的规定:

- 舰船血量状态 `Timer.ship_status` : 0 为绿血，1 为黄血，2 为红血，-1 为不存在
- 敌方阵容字典 `Timer.enemy_type_count` : keys() 为所有舰船类型，item 结构为 (类型, 数量)，可以参考 `DecisionBlock`  类中的 `old_version` 成员函数



