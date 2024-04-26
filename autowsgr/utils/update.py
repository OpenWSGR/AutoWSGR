import os
import subprocess
import time

import inquirer
import pkg_resources
import requests
from packaging.version import parse

update_source = [
    inquirer.List(
        "source",
        message="Please choose the source to update",
        choices=["北京外国语(推荐)", "清华源", "PyPI"],
    ),
]


def check_for_updates():
    print("Checking for updates...")
    # 获取本地autowsgr版本号
    local_version = get_local_version()

    # 发送 GET 请求获取库的元数据信息
    response = requests.get("https://mirrors.bfsu.edu.cn/pypi/web/json/autowsgr")
    data = response.json()

    # 提取最新版本号
    latest_version = data["info"]["version"]
    # 比较版本号
    if parse(local_version) < parse(latest_version):
        update_questions = [
            inquirer.List(
                "source",
                message=f"New version {latest_version} is available.Your version is {local_version}. Do you want to update?",
                choices=["Yes", "No"],
            ),
        ]
        result = get_user_choice(update_questions)
        if result == "Yes":
            # 选择使用哪个源更新,输出按钮回车选择
            choice = get_user_choice(update_source)
            update_library(choice)
            print("更新完成，稍后将自动退出，请重新启动脚本")
            time.sleep(5)
            os._exit(0)  # 更新成功后退出脚本
    else:
        print("You are using the latest version of the library.")


def get_local_version():
    # 使用pkg_resources获取本地库的版本号
    try:
        version = pkg_resources.get_distribution("autowsgr").version
        return version
    except Exception as e:
        print(f"Failed to get the local version.Error: {e}")
        return


def get_user_choice(questions):
    answers = inquirer.prompt(questions)
    return answers["source"]


def update_library(choice="PyPI"):
    choice_list = {
        "PyPI": ["pip", "install", "--upgrade", "--index-url", "https://pypi.org/simple", "autowsgr"],
        "北京外国语(推荐)": ["pip", "install", "--index-url", "https://mirrors.bfsu.edu.cn/pypi/web/simple/", "--upgrade", "autowsgr"],
        "清华源": ["pip", "install", "--index-url", "https://pypi.tuna.tsinghua.edu.cn/simple", "--upgrade", "autowsgr"],
    }
    subprocess.run(choice_list[choice])


# if __name__ == "__main__":
#     check_for_updates()
