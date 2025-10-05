import locale
import os
import sys
import traceback

from PyQt6.QtCore import QEvent, QObject, QProcess, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedSeq
from ruamel.yaml.scalarstring import DoubleQuotedScalarString


# gui早期版本
# 全局变量和常量
CONFIG_FILE = 'user_settings.yaml'
PLANS_DIR = './plans/normal_fight/'

# 按类别划分的舰种
SHIP_TYPE_CATEGORIES = {
    '大型': ['航母', '装母', '战列', '航战', '战巡', '大巡', '导战'],
    '中型': ['轻母', '重巡', '航巡', '雷巡', '轻巡', '导巡', '防巡'],
    '小型': ['重炮', '驱逐', '导潜', '潜艇', '炮潜', '补给', '导驱', '防驱'],
    '其他': ['其他'],
}

ALL_SHIP_TYPES = [ship for sublist in SHIP_TYPE_CATEGORIES.values() for ship in sublist]

BATTLE_TYPES = [
    '普通驱逐',
    '困难驱逐',
    '普通巡洋',
    '困难巡洋',
    '普通战列',
    '困难战列',
    '普通航母',
    '困难航母',
    '普通潜艇',
    '困难潜艇',
]


### 屏蔽滚轮 ###
class GlobalWheelEventFilter(QObject):
    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Wheel and isinstance(watched, (QComboBox, QSpinBox)):
            # 返回 True 表示该事件已被处理，不要再进一步传递，从而过滤滚轮事件
            return True
        # 对于所有其他控件或事件，返回默认的事件处理
        return super().eventFilter(watched, event)


### 黑/白名单二级框 ###
class ShipTypesDialog(QDialog):
    """用于多选舰种的弹出对话框，带分类和全选功能"""

    types_selected = pyqtSignal(object)

    def __init__(self, selected_types, parent=None):
        super().__init__(parent)
        self.setWindowTitle('选择舰种')
        self.setMinimumWidth(600)  # 调整宽度以适应5列布局

        # 存储所有舰种复选框，方便最后收集结果
        self.ship_checkboxes = []
        # 映射：分类全选框 -> 其包含的舰种复选框列表
        self.category_map = {}

        dialog_layout = QVBoxLayout(self)

        # 创建一个可滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        dialog_layout.addWidget(scroll_area)

        scroll_widget = QWidget()
        main_layout = QVBoxLayout(scroll_widget)
        scroll_area.setWidget(scroll_widget)

        # 遍历类别并创建UI
        for category_name, ship_list in SHIP_TYPE_CATEGORIES.items():
            group_box = QGroupBox(category_name)
            group_layout = QVBoxLayout(group_box)

            category_checkbox = QCheckBox('全选/全不选')
            category_checkbox.setTristate(True)
            group_layout.addWidget(category_checkbox)

            grid_layout = QGridLayout()
            child_checkboxes = []

            for i, ship_type in enumerate(ship_list):
                checkbox = QCheckBox(ship_type)
                checkbox.setChecked(ship_type in selected_types)
                grid_layout.addWidget(checkbox, i // 5, i % 5)
                self.ship_checkboxes.append(checkbox)
                child_checkboxes.append(checkbox)

            group_layout.addLayout(grid_layout)
            self.category_map[category_checkbox] = child_checkboxes

            # --- 信号连接 ---
            # 连接分类全选框的信号
            category_checkbox.stateChanged.connect(
                lambda state, cb=category_checkbox: self.on_category_toggled(cb)
            )
            # 连接每个舰种复选框的信号
            for child_cb in child_checkboxes:
                child_cb.toggled.connect(
                    lambda state, parent_cb=category_checkbox: self.update_category_state(parent_cb)
                )

            # 初始化时更新一次父复选框的状态
            self.update_category_state(category_checkbox)

            main_layout.addWidget(group_box)

        main_layout.addStretch()

        # 确定/取消 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)
        ok_button.setText('确定')
        cancel_button.setText('取消')
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        dialog_layout.addWidget(button_box)

    def on_category_toggled(self, category_checkbox):
        """当分类全选框被点击时，更新所有子项的状态"""

        # 检查复选框被点击后的当前状态
        if category_checkbox.checkState() == Qt.CheckState.Unchecked:
            new_child_state = False
        else:
            new_child_state = True

        # 将决定的状态应用到所有子复选框
        child_checkboxes = self.category_map[category_checkbox]
        for cb in child_checkboxes:
            cb.blockSignals(True)  # 阻塞信号，防止循环触发
            cb.setChecked(new_child_state)
            cb.blockSignals(False)

        # 在逻辑执行完毕后，调用 update_category_state 同步父复选框的最终状态
        self.update_category_state(category_checkbox)

    def update_category_state(self, category_checkbox):
        """当子项状态改变时，更新分类全选框的状态（三态）"""
        category_checkbox.blockSignals(True)  # 阻塞父复选框信号，防止循环触发

        child_checkboxes = self.category_map[category_checkbox]
        checked_count = sum(1 for cb in child_checkboxes if cb.isChecked())

        if checked_count == 0:
            category_checkbox.setCheckState(Qt.CheckState.Unchecked)
        elif checked_count == len(child_checkboxes):
            category_checkbox.setCheckState(Qt.CheckState.Checked)
        else:
            category_checkbox.setCheckState(Qt.CheckState.PartiallyChecked)

        category_checkbox.blockSignals(False)

    def accept(self):
        """当点击OK时，收集所有选中的舰种并发送信号"""
        selected = [cb.text() for cb in self.ship_checkboxes if cb.isChecked()]
        cs = CommentedSeq(selected)
        self.types_selected.emit(cs)
        super().accept()


### 添加任务二级框 ###
class AddTaskDialog(QDialog):
    """用于添加或编辑常规战任务的弹出对话框"""

    def __init__(self, task_data=None, parent=None):
        super().__init__(parent)

        self.task_file_combo = QComboBox()
        self.fleet_spinbox = QSpinBox()
        self.count_spinbox = QSpinBox()

        self.setup_ui()
        self.load_task_files()

        if task_data:
            self.setWindowTitle('编辑常规战任务')
            task_name = str(task_data[0])
            found_index = self.task_file_combo.findText(task_name, Qt.MatchFlag.MatchStartsWith)
            if found_index != -1:
                self.task_file_combo.setCurrentIndex(found_index)

            self.fleet_spinbox.setValue(int(task_data[1]))
            self.count_spinbox.setValue(int(task_data[2]))
        else:
            self.setWindowTitle('添加常规战任务')

    def setup_ui(self):
        layout = QFormLayout(self)
        self.fleet_spinbox.setRange(1, 4)
        self.count_spinbox.setRange(1, 99999)

        layout.addRow('任务:', self.task_file_combo)
        layout.addRow('出征舰队:', self.fleet_spinbox)
        layout.addRow('出征次数:', self.count_spinbox)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)
        ok_button.setText('确定')
        cancel_button.setText('取消')
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

    def load_task_files(self):
        """从./plans/normal_fight/目录加载文件名到下拉菜单"""
        if not os.path.isdir(PLANS_DIR):
            QMessageBox.warning(
                self, '目录未找到', f'未找到任务文件夹: {PLANS_DIR}\n请创建该文件夹并放入任务文件。'
            )
            self.task_file_combo.addItem('未找到任务文件夹')
            self.task_file_combo.setEnabled(False)
            return

        try:
            files = [f for f in os.listdir(PLANS_DIR) if f.endswith(('.yml', '.yaml'))]
            if not files:
                self.task_file_combo.addItem('未找到任务文件')
                self.task_file_combo.setEnabled(False)
            else:
                plan_names = [os.path.splitext(f)[0] for f in files]
                self.task_file_combo.addItems(plan_names)
        except Exception as e:
            QMessageBox.critical(self, '错误', f'读取任务文件时出错: {e}')

    def get_task_data(self):
        """获取对话框中配置的任务数据"""
        if not self.task_file_combo.isEnabled():
            return None

        task_name = self.task_file_combo.currentText()
        if '.' in task_name:
            task_name = os.path.splitext(task_name)[0]

        task_data = CommentedSeq(
            [task_name, self.fleet_spinbox.value(), self.count_spinbox.value()]
        )
        task_data.fa.set_flow_style()
        return task_data


### 主页 ###
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.yaml = YAML()
        self.yaml.preserve_quotes = True
        self.yaml.default_flow_style = False
        self.yaml.indent(mapping=2, sequence=4, offset=2)
        self.yaml.boolean_representation = ['False', 'True']

        # 日常
        self.daily_task_process = QProcess(self)
        self.daily_task_process.finished.connect(self.on_daily_task_finished)
        self.daily_task_process.readyReadStandardOutput.connect(self.update_ad_log_display)
        self.daily_task_process.readyReadStandardError.connect(self.update_ad_log_display)
        self.log_encoding = locale.getpreferredencoding()
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)

        # 决战
        self.db_process = QProcess(self)
        self.db_process.finished.connect(self.on_db_finished)
        self.db_process.readyReadStandardOutput.connect(self.update_db_log_display)
        self.db_process.readyReadStandardError.connect(self.update_db_log_display)
        self.db_log_display = QTextEdit()
        self.db_log_display.setReadOnly(True)

        # 活动
        self.event_process = QProcess(self)
        self.event_process.finished.connect(self.on_event_finished)
        self.event_process.readyReadStandardOutput.connect(self.update_event_log_display)
        self.event_process.readyReadStandardError.connect(self.update_event_log_display)
        self.event_log_display = QTextEdit()
        self.event_log_display.setReadOnly(True)

        self.config_data = self.load_config()
        self.init_ui()
        self.update_ui_from_config()

    def load_config(self):
        try:
            with open(CONFIG_FILE, encoding='utf-8') as f:
                return self.yaml.load(f)
        except FileNotFoundError:
            raise SystemExit(f"错误: 配置文件 '{CONFIG_FILE}' 未找到。请确保它和程序在同一目录下。")

    def save_config(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                self.yaml.dump(self.config_data, f)
        except Exception as e:
            print(f'保存失败: {e}')

    def init_ui(self):
        self.setWindowTitle('AutoWSGR GUI')
        self.setGeometry(100, 100, 800, 750)

        self.setFont(QFont('Microsoft YaHei', 10))
        self.setStyleSheet("""
            QGroupBox { font-weight: bold; border: 1px solid #cccccc; border-radius: 5px; margin-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; background-color: #f0f0f0; border-radius: 5px; }
            QPushButton { padding: 5px 15px; border-radius: 4px; background-color: #0078d7; color: white; font-weight: bold; }
            QPushButton:hover { background-color: #005a9e; }
            QTableWidget { gridline-color: #dcdcdc; }
            QTabWidget::pane { border-top: 1px solid #cccccc; }
            QTabBar::tab { padding: 8px 20px; }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        main_layout.addWidget(self.create_top_config_group())

        tabs = QTabWidget()
        tabs.addTab(self.create_daily_auto_tab(), '日常挂机设置')
        tabs.addTab(self.create_decisive_battle_tab(), '决战设置')
        tabs.addTab(self.create_event_tab(), '活动设置')

        main_layout.addWidget(tabs)

    def update_config_value(self, path, value):
        keys = path.split('.')
        d = self.config_data
        for key in keys[:-1]:
            d = d[key]
        d[keys[-1]] = value
        self.save_config()

    def create_top_config_group(self):
        group = QGroupBox('全局设置')
        layout = QGridLayout(group)

        # 初始化所有需要用到的控件
        self.debug_cb = QCheckBox('启用Debug模式')
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])
        self.check_update_cb = QCheckBox('检查更新')
        self.dock_full_destroy_cb = QCheckBox('船坞满时解装')
        self.destroy_ship_work_mode_combo = QComboBox()
        items = [('不启用', 0), ('黑名单', 1), ('白名单', 2)]
        self.destroy_ship_work_mode_combo.addItems([item[0] for item in items])
        self.destroy_ship_types_btn = QPushButton('编辑黑/白名单')
        self.bathroom_feature_count_spin = QSpinBox()
        self.bathroom_feature_count_spin.setRange(0, 4)
        self.bathroom_count_spin = QSpinBox()
        self.bathroom_count_spin.setRange(0, 12)
        self.emulator_type_combo = QComboBox()
        self.emulator_type_combo.addItems(['蓝叠', '雷电', 'MuMu', '夜神', '逍遥'])
        self.emulator_name_label = QLabel('MuMu 地址:')
        self.emulator_name_input = QLineEdit()
        self.emulator_name_input.setPlaceholderText('例如: 127.0.0.1:7555')

        # 创建带标签的组合控件
        log_level_layout = QHBoxLayout()
        log_level_layout.addWidget(QLabel('日志级别:'))
        log_level_layout.addWidget(self.log_level_combo)

        destroy_mode_layout = QHBoxLayout()
        destroy_mode_layout.addWidget(QLabel('解装模式:'))
        destroy_mode_layout.addWidget(self.destroy_ship_work_mode_combo)

        bathroom_feature_layout = QHBoxLayout()
        bathroom_feature_layout.addWidget(QLabel('浴室数量:'))
        bathroom_feature_layout.addWidget(self.bathroom_feature_count_spin)

        bathroom_count_layout = QHBoxLayout()
        bathroom_count_layout.addWidget(QLabel('修理总数:'))
        bathroom_count_layout.addWidget(self.bathroom_count_spin)

        emulator_type_layout = QHBoxLayout()
        emulator_type_layout.addWidget(QLabel('模拟器类型:'))
        emulator_type_layout.addWidget(self.emulator_type_combo)

        # 创建垂直分割线
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.Shape.VLine)
        separator1.setFrameShadow(QFrame.Shadow.Sunken)

        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.VLine)
        separator2.setFrameShadow(QFrame.Shadow.Sunken)

        # 添加控件到网格
        # 第1列控件
        layout.addWidget(self.check_update_cb, 0, 0)
        layout.addWidget(self.debug_cb, 1, 0)
        layout.addLayout(log_level_layout, 2, 0)

        # 第1个分割线
        layout.addWidget(separator1, 0, 1, 3, 1)

        # 第2列控件
        layout.addWidget(self.dock_full_destroy_cb, 0, 2)
        layout.addLayout(destroy_mode_layout, 1, 2)
        layout.addWidget(self.destroy_ship_types_btn, 2, 2)

        # 第2个分割线
        layout.addWidget(separator2, 0, 3, 3, 1)

        # 第3列控件
        layout.addLayout(bathroom_feature_layout, 0, 4)
        layout.addLayout(bathroom_count_layout, 1, 4)
        layout.addLayout(emulator_type_layout, 2, 4)

        # MuMu模拟器的专用输入行
        layout.addWidget(self.emulator_name_label, 3, 0)
        layout.addWidget(self.emulator_name_input, 3, 1, 1, 4)

        # 连接所有控件的信号到槽函数
        self.debug_cb.toggled.connect(lambda checked: self.update_config_value('debug', checked))
        self.log_level_combo.currentTextChanged.connect(
            lambda text: self.update_config_value('log_level', text)
        )
        self.check_update_cb.toggled.connect(
            lambda checked: self.update_config_value('check_update', checked)
        )
        self.dock_full_destroy_cb.toggled.connect(
            lambda checked: self.update_config_value('dock_full_destroy', checked)
        )
        self.destroy_ship_work_mode_combo.currentIndexChanged.connect(
            lambda index: self.update_config_value('destroy_ship_work_mode', items[index][1])
        )
        self.destroy_ship_types_btn.clicked.connect(self.open_ship_types_dialog)
        self.bathroom_feature_count_spin.valueChanged.connect(
            lambda val: self.update_config_value('bathroom_feature_count', val)
        )
        self.bathroom_count_spin.valueChanged.connect(
            lambda val: self.update_config_value('bathroom_count', val)
        )
        self.emulator_type_combo.currentTextChanged.connect(self.on_emulator_changed)
        self.emulator_name_input.textChanged.connect(
            lambda text: self.update_config_value('emulator_name', text)
        )

        return group

    def create_daily_auto_tab(self):
        tab_widget = QWidget()
        main_layout = QVBoxLayout(tab_widget)
        main_layout.setContentsMargins(5, 10, 5, 5)

        # 创建可分裂的顶部区域
        top_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 创建左侧面板 (设置项)
        left_panel = QWidget()
        left_layout = QFormLayout(left_panel)
        left_layout.setContentsMargins(5, 5, 5, 5)

        # “启动/中止”按钮
        self.daily_task_button = QPushButton('启动日常挂机')
        self.daily_task_button.clicked.connect(self.on_daily_task_toggle)
        left_layout.addRow(self.daily_task_button)

        # 初始化所有设置控件
        self.auto_expedition_cb = QCheckBox('自动重复远征')
        self.auto_gain_bonus_cb = QCheckBox('自动收取任务奖励')
        self.auto_bath_repair_cb = QCheckBox('空闲时自动修理')
        self.auto_set_support_cb = QCheckBox('自动开启战役支援')
        self.auto_battle_cb = QCheckBox('自动每日战役')
        self.battle_type_combo = QComboBox()
        self.auto_exercise_cb = QCheckBox('自动演习')
        self.exercise_fleet_id_spin = QSpinBox()
        self.auto_normal_fight_cb = QCheckBox('按自定义任务进行常规战')
        self.quick_repair_limit_spin = QSpinBox()
        self.stop_max_ship_cb = QCheckBox('捞到每日最大掉落时停止')
        self.stop_max_loot_cb = QCheckBox('捞到每日最大胖次时停止')

        # 添加控件到左侧表单
        left_layout.addRow(self.auto_expedition_cb)
        left_layout.addRow(self.auto_gain_bonus_cb)
        left_layout.addRow(self.auto_bath_repair_cb)
        left_layout.addRow(self.auto_set_support_cb)
        left_layout.addRow(self.auto_battle_cb)
        left_layout.addRow('战役选择:', self.battle_type_combo)
        left_layout.addRow(self.auto_exercise_cb)
        left_layout.addRow('演习出征舰队:', self.exercise_fleet_id_spin)
        left_layout.addRow(self.auto_normal_fight_cb)
        left_layout.addRow('快修消耗上限 (0为无上限):', self.quick_repair_limit_spin)
        left_layout.addRow(self.stop_max_ship_cb)
        left_layout.addRow(self.stop_max_loot_cb)

        # 信号连接
        self.auto_expedition_cb.toggled.connect(
            lambda checked: self.update_config_value('daily_automation.auto_expedition', checked)
        )
        self.auto_gain_bonus_cb.toggled.connect(
            lambda checked: self.update_config_value('daily_automation.auto_gain_bonus', checked)
        )
        self.auto_bath_repair_cb.toggled.connect(
            lambda checked: self.update_config_value('daily_automation.auto_bath_repair', checked)
        )
        self.auto_set_support_cb.toggled.connect(
            lambda checked: self.update_config_value('daily_automation.auto_set_support', checked)
        )
        self.auto_battle_cb.toggled.connect(
            lambda checked: self.update_config_value('daily_automation.auto_battle', checked)
        )
        self.auto_exercise_cb.toggled.connect(
            lambda checked: self.update_config_value('daily_automation.auto_exercise', checked)
        )
        self.auto_normal_fight_cb.toggled.connect(
            lambda checked: self.update_config_value('daily_automation.auto_normal_fight', checked)
        )
        self.stop_max_ship_cb.toggled.connect(
            lambda checked: self.update_config_value('daily_automation.stop_max_ship', checked)
        )
        self.stop_max_loot_cb.toggled.connect(
            lambda checked: self.update_config_value('daily_automation.stop_max_loot', checked)
        )
        self.battle_type_combo.addItems(BATTLE_TYPES)
        self.battle_type_combo.currentTextChanged.connect(
            lambda text: self.update_config_value('daily_automation.battle_type', text)
        )
        self.exercise_fleet_id_spin.setRange(1, 4)
        self.exercise_fleet_id_spin.valueChanged.connect(
            lambda val: self.update_config_value('daily_automation.exercise_fleet_id', val)
        )
        self.quick_repair_limit_spin.setRange(0, 9999)
        self.quick_repair_limit_spin.valueChanged.connect(
            lambda val: self.update_config_value(
                'daily_automation.quick_repair_limit', None if val == 0 else val
            )
        )

        # 将左侧面板和右侧日志框添加到分裂器中
        top_splitter.addWidget(left_panel)
        top_splitter.addWidget(self.log_display)
        top_splitter.setSizes([250, 500])

        # 创建底部区域
        self.tasks_table = QTableWidget()
        self.tasks_table.setColumnCount(3)
        self.tasks_table.setHorizontalHeaderLabels(['任务', '舰队', '次数'])
        self.tasks_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tasks_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tasks_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tasks_table.setMinimumHeight(150)

        tasks_buttons_layout = QHBoxLayout()
        add_task_btn = QPushButton('添加任务')
        edit_task_btn = QPushButton('编辑选中任务')
        remove_task_btn = QPushButton('删除选中任务')
        add_task_btn.clicked.connect(self.open_add_task_dialog)
        edit_task_btn.clicked.connect(self.open_edit_task_dialog)
        remove_task_btn.clicked.connect(self.remove_task_row)
        tasks_buttons_layout.addStretch()
        tasks_buttons_layout.addWidget(add_task_btn)
        tasks_buttons_layout.addWidget(edit_task_btn)
        tasks_buttons_layout.addWidget(remove_task_btn)

        # 将分裂器和底部控件添加到主布局
        main_layout.addWidget(top_splitter)
        main_layout.addWidget(QLabel('常规战自定义任务列表:'))
        main_layout.addWidget(self.tasks_table)
        main_layout.addLayout(tasks_buttons_layout)

        return tab_widget

    def create_decisive_battle_tab(self):
        # 创建一个父控件和主布局
        tab_widget = QWidget()
        main_layout = QVBoxLayout(tab_widget)
        main_layout.setContentsMargins(5, 10, 5, 5)

        # 主垂直分割，用于控制日志区域高度
        v_splitter = QSplitter(Qt.Orientation.Vertical)

        # 水平分割 (设置项 + 日志)
        top_h_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧面板 (设置项)
        left_panel = QWidget()
        left_layout = QFormLayout(left_panel)
        left_layout.setContentsMargins(5, 5, 5, 5)

        self.db_start_button = QPushButton('启动决战')
        self.db_sortie_count_spin = QSpinBox()
        self.db_chapter_spin = QSpinBox()
        self.db_repair_level_combo = QComboBox()
        self.db_full_destroy_cb = QCheckBox('船坞满时解装(仅决战)')
        self.db_useful_skill_cb = QCheckBox('充分利用教官技能')

        self.db_sortie_count_spin.setRange(1, 999)
        self.db_chapter_spin.setRange(1, 6)
        items = [('中破修', 1), ('大破修', 2)]
        self.db_repair_level_combo.addItems([item[0] for item in items])

        left_layout.addRow(self.db_start_button)
        left_layout.addRow('出击次数:', self.db_sortie_count_spin)
        left_layout.addRow('决战章节:', self.db_chapter_spin)
        left_layout.addRow('维修策略:', self.db_repair_level_combo)
        left_layout.addRow(self.db_full_destroy_cb)
        left_layout.addRow(self.db_useful_skill_cb)

        top_h_splitter.addWidget(left_panel)
        top_h_splitter.addWidget(self.db_log_display)
        top_h_splitter.setSizes([250, 500])

        # 舰队配置
        bottom_widget = QWidget()
        bottom_hbox_layout = QHBoxLayout(bottom_widget)
        bottom_hbox_layout.setContentsMargins(0, 10, 0, 0)

        bottom_group = QGroupBox('舰队配置')
        bottom_form_layout = QFormLayout(bottom_group)
        self.db_level1_input = QLineEdit()
        self.db_level2_input = QLineEdit()
        self.db_flagship_priority_input = QLineEdit()
        placeholder = '用英文逗号 , 分隔'
        self.db_level1_input.setPlaceholderText(placeholder)
        self.db_level2_input.setPlaceholderText(placeholder)
        self.db_flagship_priority_input.setPlaceholderText(placeholder)
        bottom_form_layout.addRow('一级舰队:', self.db_level1_input)
        bottom_form_layout.addRow('二级舰队:', self.db_level2_input)
        bottom_form_layout.addRow('旗舰优先级:', self.db_flagship_priority_input)

        self.db_fleet_check_label = QLabel('等待输入...')
        self.db_fleet_check_label.setWordWrap(True)
        self.db_fleet_check_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.db_fleet_check_label.setFrameShape(QFrame.Shape.StyledPanel)
        self.db_fleet_check_label.setMinimumWidth(200)

        bottom_hbox_layout.addWidget(bottom_group, 3)
        bottom_hbox_layout.addWidget(self.db_fleet_check_label, 1)

        # 组装垂直分割
        v_splitter.addWidget(top_h_splitter)
        v_splitter.addWidget(bottom_widget)
        v_splitter.setSizes([350, 150])  # 设置初始高度比例

        # 将主分割控件添加到主布局中
        main_layout.addWidget(v_splitter)

        # 信号连接
        self.db_start_button.clicked.connect(self.on_db_toggle)
        self.db_sortie_count_spin.valueChanged.connect(
            lambda val: self.update_config_value('decisive_battle.sortie_times', val)
        )
        self.db_chapter_spin.valueChanged.connect(
            lambda val: self.update_config_value('decisive_battle.chapter', val)
        )
        self.db_repair_level_combo.currentIndexChanged.connect(
            lambda index: self.update_config_value('decisive_battle.repair_level', items[index][1])
        )
        self.db_full_destroy_cb.toggled.connect(
            lambda checked: self.update_config_value('decisive_battle.full_destroy', checked)
        )
        self.db_useful_skill_cb.toggled.connect(
            lambda checked: self.update_config_value('decisive_battle.useful_skill', checked)
        )
        self.db_level1_input.textChanged.connect(
            lambda text: self.update_list_config('decisive_battle.level1', text)
        )
        self.db_level2_input.textChanged.connect(
            lambda text: self.update_list_config('decisive_battle.level2', text)
        )
        self.db_flagship_priority_input.textChanged.connect(
            lambda text: self.update_list_config('decisive_battle.flagship_priority', text)
        )
        self.db_chapter_spin.valueChanged.connect(self.check_decisive_battle_fleet)
        self.db_level1_input.textChanged.connect(self.check_decisive_battle_fleet)
        self.db_level2_input.textChanged.connect(self.check_decisive_battle_fleet)
        self.db_flagship_priority_input.textChanged.connect(self.check_decisive_battle_fleet)

        return tab_widget

    def create_event_tab(self):
        tab_widget = QWidget()
        main_layout = QVBoxLayout(tab_widget)
        main_layout.setContentsMargins(5, 10, 5, 5)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left_panel = QWidget()
        left_layout = QFormLayout(left_panel)
        left_layout.setContentsMargins(5, 5, 5, 5)

        # 初始化所有控件
        self.event_start_button = QPushButton('启动活动')
        self.event_folder_combo = QComboBox()
        self.event_task_combo = QComboBox()
        self.event_fleet_id_spin = QSpinBox()
        self.event_battle_count_spin = QSpinBox()

        self.event_fleet_id_spin.setRange(1, 4)
        self.event_battle_count_spin.setRange(1, 9999)

        left_layout.addRow(self.event_start_button)
        left_layout.addRow('选择活动:', self.event_folder_combo)
        left_layout.addRow('选择任务:', self.event_task_combo)
        left_layout.addRow('出征舰队:', self.event_fleet_id_spin)
        left_layout.addRow('战斗次数:', self.event_battle_count_spin)

        splitter.addWidget(left_panel)
        splitter.addWidget(self.event_log_display)
        splitter.setSizes([250, 500])
        splitter.setFixedHeight(394)

        main_layout.addWidget(splitter)
        main_layout.addStretch()

        # 添加一个很酷的字符画
        ascii_art_string = r"""
█████╗ ██╗   ██╗████████╗ ██████╗ ██╗    ██╗███████╗ ██████╗ ██████╗
██╔══██╗██║   ██║╚══██╔══╝██╔═══██╗██║    ██║██╔════╝██╔════╝ ██╔══██╗
███████║██║   ██║   ██║   ██║   ██║██║ █╗ ██║███████╗██║  ███╗██████╔╝
██╔══██║██║   ██║   ██║   ██║   ██║██║███╗██║╚════██║██║   ██║██╔══██╗
██║  ██║╚██████╔╝   ██║   ╚██████╔╝╚███╔███╔╝███████║╚██████╔╝██║  ██║
╚═╝  ╚═╝ ╚═════╝    ╚═╝    ╚═════╝  ╚══╝╚══╝ ╚══════╝ ╚═════╝ ╚═╝  ╚═╝
"""
        ascii_label = QLabel(ascii_art_string)
        monospace_font = QFont('Courier New', 8)
        ascii_label.setFont(monospace_font)
        ascii_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(ascii_label)

        # 信号连接
        self.event_start_button.clicked.connect(self.on_event_toggle)
        self.event_folder_combo.currentTextChanged.connect(self.on_event_folder_changed)
        self.event_task_combo.currentTextChanged.connect(
            lambda text: self.update_config_value('event_automation.plan_name', text)
            if text
            else None
        )
        self.event_fleet_id_spin.valueChanged.connect(
            lambda val: self.update_config_value('event_automation.fleet_id', val)
        )
        self.event_battle_count_spin.valueChanged.connect(
            lambda val: self.update_config_value('event_automation.battle_count', val)
        )

        return tab_widget

    ## 加载初始项 ##
    def update_ui_from_config(self):
        """用加载的配置数据初始化所有UI控件的值"""
        # 全局
        self.check_update_cb.setChecked(self.config_data.get('check_update', False))
        self.dock_full_destroy_cb.setChecked(self.config_data.get('dock_full_destroy', False))
        self.debug_cb.setChecked(self.config_data.get('debug', False))
        self.destroy_ship_work_mode_combo.setCurrentIndex(
            self.config_data.get('destroy_ship_work_mode', 0)
        )
        self.bathroom_feature_count_spin.setValue(self.config_data.get('bathroom_feature_count', 3))
        self.bathroom_count_spin.setValue(self.config_data.get('bathroom_count', 8))
        self.log_level_combo.setCurrentText(self.config_data.get('log_level', 'DEBUG'))
        # 模拟器
        emu_type = self.config_data.get('emulator_type', '蓝叠')
        self.emulator_type_combo.setCurrentText(emu_type)
        self.on_emulator_changed(emu_type, update_config=False)
        self.emulator_name_input.setText(self.config_data.get('emulator_name', ''))
        # 日常
        daily = self.config_data.get('daily_automation', {})
        self.auto_expedition_cb.setChecked(daily.get('auto_expedition', False))
        self.auto_gain_bonus_cb.setChecked(daily.get('auto_gain_bonus', False))
        self.auto_bath_repair_cb.setChecked(daily.get('auto_bath_repair', False))
        self.auto_set_support_cb.setChecked(daily.get('auto_set_support', False))
        self.auto_battle_cb.setChecked(daily.get('auto_battle', False))
        self.auto_exercise_cb.setChecked(daily.get('auto_exercise', False))
        self.auto_normal_fight_cb.setChecked(daily.get('auto_normal_fight', False))
        self.stop_max_ship_cb.setChecked(daily.get('stop_max_ship', False))
        self.stop_max_loot_cb.setChecked(daily.get('stop_max_loot', False))

        self.battle_type_combo.setCurrentText(daily.get('battle_type', '困难战列'))
        self.exercise_fleet_id_spin.setValue(daily.get('exercise_fleet_id', 3))
        self.quick_repair_limit_spin.setValue(daily.get('quick_repair_limit') or 0)
        self.populate_tasks_table(daily.get('normal_fight_tasks', []))
        # 决战
        decisive = self.config_data.get('decisive_battle', {})
        self.db_chapter_spin.setValue(decisive.get('chapter', 6))
        self.db_sortie_count_spin.setValue(decisive.get('sortie_times', 1))
        self.db_level1_input.setText(', '.join(map(str, decisive.get('level1', []))))
        self.db_level2_input.setText(', '.join(map(str, decisive.get('level2', []))))
        self.db_flagship_priority_input.setText(
            ', '.join(map(str, decisive.get('flagship_priority', [])))
        )
        self.db_repair_level_combo.setCurrentIndex(decisive.get('repair_level', 2) - 1)
        self.db_full_destroy_cb.setChecked(decisive.get('full_destroy', False))
        self.db_useful_skill_cb.setChecked(decisive.get('useful_skill', False))
        self.check_decisive_battle_fleet()
        # 活动
        event = self.config_data.get('event_automation', {})
        # 1. 禁用文件夹下拉框信号，填充并设置其来自配置的值
        self.event_folder_combo.blockSignals(True)
        self.populate_event_folders_combo()
        saved_folder = event.get('event_folder')
        if saved_folder and self.event_folder_combo.findText(saved_folder) != -1:
            self.event_folder_combo.setCurrentText(saved_folder)
        self.event_folder_combo.blockSignals(False)
        # 2. 禁用任务下拉框信号，手动填充并设置其来自配置的值
        self.event_task_combo.blockSignals(True)
        # 手动调用处理函数，以当前选中的文件夹填充任务列表
        self.on_event_folder_changed(self.event_folder_combo.currentText(), update_config=False)
        saved_plan = event.get('plan_name')
        if saved_plan and self.event_task_combo.findText(saved_plan) != -1:
            self.event_task_combo.setCurrentText(saved_plan)
        self.event_task_combo.blockSignals(False)

        # 3. 设置其余控件
        self.event_fleet_id_spin.setValue(event.get('fleet_id', 1))
        self.event_battle_count_spin.setValue(event.get('battle_count', 100))

    ## 全局相关 ##

    def on_emulator_changed(self, text, update_config=True):
        is_mumu = text == 'MuMu'
        self.emulator_name_label.setVisible(is_mumu)
        self.emulator_name_input.setVisible(is_mumu)
        if update_config:
            self.update_config_value('emulator_type', text)

    def open_ship_types_dialog(self):
        current_types = self.config_data.get('destroy_ship_types', [])
        dialog = ShipTypesDialog(current_types, self)
        dialog.types_selected.connect(
            lambda types: self.update_config_value('destroy_ship_types', types)
        )
        dialog.exec()

    def populate_tasks_table(self, tasks):
        self.tasks_table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            for col, item in enumerate(task):
                self.tasks_table.setItem(row, col, QTableWidgetItem(str(item)))

    ## 日常相关 ##

    def on_daily_task_toggle(self):
        """处理“启动/中止日常挂机”按钮的点击事件"""
        if self.daily_task_process.state() == QProcess.ProcessState.Running:
            self.daily_task_process.kill()
        else:
            if (
                self.db_process.state() == QProcess.ProcessState.Running
                or self.event_process.state() == QProcess.ProcessState.Running
            ):
                QMessageBox.warning(self, '操作失败', '已有其他任务正在运行，请先中止。')
                return
            script_path = 'auto_daily.py'
            if not os.path.exists(script_path):
                QMessageBox.warning(self, '文件未找到', f'无法找到脚本: {script_path}')
                return

            # 启动前清空日志
            self.log_display.clear()
            self.daily_task_button.setText('中止日常挂机')
            self.daily_task_button.setStyleSheet('background-color: #d73737; color: white;')

            self.daily_task_process.start(sys.executable, [script_path])

    def on_daily_task_finished(self):
        """当脚本进程结束时（无论是正常结束、崩溃还是被中止），重置按钮状态"""
        self.daily_task_button.setText('启动日常挂机')
        self.daily_task_button.setStyleSheet('')
        self.log_display.append('\n--- 任务已结束 ---')

    def update_ad_log_display(self):
        """
        读取进程输出并将其显示在日志框中。
        使用系统本地编码以支持中文，并确保日志自动滚动。
        """
        # 从进程中读取所有可用的标准输出和标准错误
        output_bytes = self.daily_task_process.readAllStandardOutput()
        error_bytes = self.daily_task_process.readAllStandardError()

        # 使用获取到的系统编码来解码字节流，忽略无法解码的字符
        output_text = output_bytes.data().decode(self.log_encoding, errors='ignore')
        error_text = error_bytes.data().decode(self.log_encoding, errors='ignore')

        full_text = output_text + error_text

        if full_text:
            # 移动光标到文本末尾
            self.log_display.moveCursor(QTextCursor.MoveOperation.End)
            # 插入新文本
            self.log_display.insertPlainText(full_text)
            # 确保滚动条始终在最下方，以显示最新日志
            self.log_display.verticalScrollBar().setValue(
                self.log_display.verticalScrollBar().maximum()
            )

    def remove_task_row(self):
        current_row = self.tasks_table.currentRow()
        if current_row > -1:
            current_tasks = self.config_data['daily_automation']['normal_fight_tasks']
            del current_tasks[current_row]
            self.update_config_value('daily_automation.normal_fight_tasks', current_tasks)
            self.populate_tasks_table(current_tasks)
        else:
            QMessageBox.information(self, '无选择', '请先在表格中选择一个要删除的任务。')

    def open_add_task_dialog(self):
        dialog = AddTaskDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_task_data = dialog.get_task_data()
            if new_task_data:
                current_tasks = self.config_data['daily_automation'].get('normal_fight_tasks', [])
                current_tasks.append(new_task_data)

                self.update_config_value('daily_automation.normal_fight_tasks', current_tasks)
                self.populate_tasks_table(current_tasks)

    def open_edit_task_dialog(self):
        current_row = self.tasks_table.currentRow()
        if current_row < 0:
            QMessageBox.information(self, '无选择', '请先在表格中选择一个要编辑的任务。')
            return

        current_tasks = self.config_data['daily_automation'].get('normal_fight_tasks', [])
        task_to_edit = current_tasks[current_row]

        dialog = AddTaskDialog(task_data=task_to_edit, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            edited_task = dialog.get_task_data()
            if edited_task:
                current_tasks[current_row] = edited_task
                self.update_config_value('daily_automation.normal_fight_tasks', current_tasks)
                self.populate_tasks_table(current_tasks)

    ## 决战相关 ##

    def on_db_toggle(self):
        """处理“启动/中止决战”按钮的点击事件"""
        if self.db_process.state() == QProcess.ProcessState.Running:
            self.db_process.kill()
        else:
            if (
                self.daily_task_process.state() == QProcess.ProcessState.Running
                or self.event_process.state() == QProcess.ProcessState.Running
            ):
                QMessageBox.warning(self, '操作失败', '已有其他任务正在运行，请先中止。')
                return
            script_path = 'decisive_battle_callable.py'
            if not os.path.exists(script_path):
                QMessageBox.warning(self, '文件未找到', f'无法找到脚本: {script_path}')
                return

            self.db_log_display.clear()
            self.db_start_button.setText('中止决战')
            self.db_start_button.setStyleSheet('background-color: #d73737; color: white;')

            # 获取出击次数并作为参数传递
            sortie_count = self.db_sortie_count_spin.value()
            self.db_process.start(sys.executable, [script_path, str(sortie_count)])

    def on_db_finished(self):
        """当决战脚本进程结束时，重置按钮状态"""
        self.db_start_button.setText('启动决战')
        self.db_start_button.setStyleSheet('')
        self.db_log_display.append('\n--- 决战任务已结束 ---')

    def update_db_log_display(self):
        """读取决战进程输出并显示在决战日志框中"""
        output_bytes = self.db_process.readAllStandardOutput()
        error_bytes = self.db_process.readAllStandardError()

        output_text = output_bytes.data().decode(self.log_encoding, errors='ignore')
        error_text = error_bytes.data().decode(self.log_encoding, errors='ignore')

        full_text = output_text + error_text

        if full_text:
            self.db_log_display.moveCursor(QTextCursor.MoveOperation.End)
            self.db_log_display.insertPlainText(full_text)
            self.db_log_display.verticalScrollBar().setValue(
                self.db_log_display.verticalScrollBar().maximum()
            )

    def _parse_ship_list(self, text: str):
        """辅助函数，用于从逗号分隔的字符串中解析出列表"""
        if not text or not text.strip():
            return []
        # 过滤掉因多余逗号产生的空字符串
        return [ship.strip() for ship in text.split(',') if ship.strip()]

    def update_list_config(self, path, text):
        items = [DoubleQuotedScalarString(item.strip()) for item in text.split(',') if item.strip()]
        cs = CommentedSeq(items)
        cs.fa.set_flow_style()
        self.update_config_value(path, cs)

    def check_decisive_battle_fleet(self):
        """检查决战舰队配置是否符合要求"""
        # 定义每个章节所需的固定舰队数量
        CHAPTER_REQUIREMENTS = {1: 6, 2: 6, 3: 8, 4: 8, 5: 10, 6: 10}

        try:
            chapter = self.db_chapter_spin.value()
            required_ships = CHAPTER_REQUIREMENTS.get(chapter, 10)  # 默认为第6章的要求

            # 解析一、二级舰队和旗舰
            level1_ships = self._parse_ship_list(self.db_level1_input.text())
            level2_ships = self._parse_ship_list(self.db_level2_input.text())
            flagship_ships = self._parse_ship_list(self.db_flagship_priority_input.text())

            total_ships = len(level1_ships) + len(level2_ships)
            flagship_count = len(flagship_ships)

            errors = []
            # 规则1：检查舰队总数
            if total_ships != required_ships:
                errors.append(f'舰船总数应为 {required_ships} 艘 (当前 {total_ships} 艘)')

            # 规则2：检查旗舰数量
            if flagship_count > required_ships:
                errors.append(f'旗舰数应≤ {required_ships} 艘 (当前 {flagship_count} 艘)')

            # 根据检查结果更新UI
            if not errors:
                self.db_fleet_check_label.setText('✅ 配置正确')
                self.db_fleet_check_label.setStyleSheet(
                    'color: #2e7d32; font-weight: bold; border: 1px solid #a5d6a7;'
                )
            else:
                error_str = '❌ 配置错误:\n' + '\n'.join(errors)
                self.db_fleet_check_label.setText(error_str)
                self.db_fleet_check_label.setStyleSheet(
                    'color: #c62828; font-weight: bold; border: 1px solid #ef9a9a;'
                )
        except Exception as e:
            self.db_fleet_check_label.setText(f'检查时出现异常: {e}')
            self.db_fleet_check_label.setStyleSheet('color: black;')

    ## 活动相关 ##

    def on_event_toggle(self):
        """处理“启动/中止活动”按钮的点击事件"""
        if self.event_process.state() == QProcess.ProcessState.Running:
            self.event_process.kill()
        else:
            if (
                self.daily_task_process.state() == QProcess.ProcessState.Running
                or self.db_process.state() == QProcess.ProcessState.Running
            ):
                QMessageBox.warning(self, '操作失败', '已有其他任务正在运行，请先中止。')
                return
            script_path = 'event_callable.py'
            if not os.path.exists(script_path):
                QMessageBox.warning(self, '文件未找到', f'无法找到脚本: {script_path}')
                return

            self.event_log_display.clear()
            self.event_start_button.setText('中止活动')
            self.event_start_button.setStyleSheet('background-color: #d73737; color: white;')

            # 从下拉菜单获取参数
            plan_path = self.event_task_combo.currentText()
            if not plan_path or '未找到' in plan_path:
                QMessageBox.warning(self, '参数错误', '请选择一个有效的活动任务！')
                self.on_event_finished()  # 重置按钮状态
                return

            fleet_id = str(self.event_fleet_id_spin.value())
            battle_count = str(self.event_battle_count_spin.value())

            self.event_process.start(
                sys.executable, [script_path, plan_path, fleet_id, battle_count]
            )

    def on_event_finished(self):
        """当活动脚本进程结束时，重置按钮状态"""
        self.event_start_button.setText('启动活动')
        self.event_start_button.setStyleSheet('')
        self.event_log_display.append('\n--- 活动任务已结束 ---')

    def update_event_log_display(self):
        """读取活动进程输出并显示在活动日志框中"""
        output_bytes = self.event_process.readAllStandardOutput()
        error_bytes = self.event_process.readAllStandardError()

        output_text = output_bytes.data().decode(self.log_encoding, errors='ignore')
        error_text = error_bytes.data().decode(self.log_encoding, errors='ignore')

        full_text = output_text + error_text

        if full_text:
            self.event_log_display.moveCursor(QTextCursor.MoveOperation.End)
            self.event_log_display.insertPlainText(full_text)
            self.event_log_display.verticalScrollBar().setValue(
                self.event_log_display.verticalScrollBar().maximum()
            )

    def on_event_folder_changed(self, folder_name, update_config=True):
        """当活动文件夹选择变化时，更新任务下拉菜单"""
        if not folder_name or '未找到' in folder_name or '没有可用' in folder_name:
            self.event_task_combo.clear()
            self.event_task_combo.setEnabled(False)
            return

        # 仅在用户交互时（update_config为True）才保存配置
        if update_config:
            self.update_config_value('event_automation.event_folder', folder_name)

        # 更新任务列表
        self.event_task_combo.clear()
        task_dir = os.path.join('./plans/event/', folder_name)

        if not os.path.isdir(task_dir):
            self.event_task_combo.addItem('无效的文件夹')
            self.event_task_combo.setEnabled(False)
            return

        try:
            files = [f for f in os.listdir(task_dir) if f.endswith(('.yml', '.yaml'))]
            if not files:
                self.event_task_combo.addItem('未找到任务文件')
                self.event_task_combo.setEnabled(False)
            else:
                # 提取不带扩展名的文件名
                plan_names = [os.path.splitext(f)[0] for f in files]
                self.event_task_combo.addItems(plan_names)
                self.event_task_combo.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(self, '错误', f'读取任务文件时出错: {e}')

    def populate_event_folders_combo(self):
        """填充活动文件夹的下拉菜单"""
        self.event_folder_combo.clear()
        event_dir = './plans/event/'
        if not os.path.isdir(event_dir):
            self.event_folder_combo.addItem('未找到活动文件夹')
            self.event_folder_combo.setEnabled(False)
            return

        try:
            folders = [
                d for d in os.listdir(event_dir) if os.path.isdir(os.path.join(event_dir, d))
            ]
            if not folders:
                self.event_folder_combo.addItem('没有可用的活动')
                self.event_folder_combo.setEnabled(False)
            else:
                self.event_folder_combo.addItems(folders)
                self.event_folder_combo.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(self, '错误', f'读取活动文件夹时出错: {e}')


### 异常 ###
def show_exception_dialog(exc_type, exc_value, exc_tb):
    """创建一个对话框来显示未捕获的异常"""
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Icon.Critical)
    msg.setText('程序遇到严重错误！')
    error_text = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    msg.setInformativeText('请将以下错误信息截图报告给开发者。')
    msg.setDetailedText(error_text)
    msg.setWindowTitle('程序崩溃')
    msg.exec()


if __name__ == '__main__':
    # 设置全局异常钩子，捕获所有未处理的异常
    sys.excepthook = show_exception_dialog

    app = QApplication(sys.argv)
    global_filter = GlobalWheelEventFilter()
    app.installEventFilter(global_filter)
    try:
        window = MainWindow()
        window.show()
    except Exception as e:
        # 即使excepthook存在，也在这里捕获初始化期间的异常
        show_exception_dialog(type(e), e, e.__traceback__)
        sys.exit(1)

    sys.exit(app.exec())
