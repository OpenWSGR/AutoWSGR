import os
import subprocess
import time

import pkg_resources
import requests
from packaging.version import parse


def check_for_updates():
    print("Checking for updates...")
    # 获取本地autowsgr版本号
    local_version = get_local_version()

    # 发送 GET 请求获取库的元数据信息
    response = requests.get("https://pypi.tuna.tsinghua.edu.cn/pypi/autowsgr/json")
    data = response.json()

    # 提取最新版本号
    latest_version = data["info"]["version"]

    # 比较版本号
    if parse(local_version) < parse(latest_version):
        choice = input(
            f"New version {latest_version} is available.Your version is {local_version}. Do you want to update? (y/n): "
        )
        if choice.lower() == "y":
            update_library()
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


def update_library():
    subprocess.run(["pip", "install", "--index-url", "https://pypi.tuna.tsinghua.edu.cn/simple", "--upgrade", "autowsgr"])


# if __name__ == "__main__":
#    check_for_updates()
