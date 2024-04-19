import importlib.resources as pkg_resources
import subprocess
import sys
import time

import requests
from packaging.version import parse


def check_for_updates():
    # 获取本地autowsgr版本号
    local_version = get_local_version()

    # 发送 GET 请求获取库的元数据信息
    response = requests.get("https://pypi.org/pypi/autowsgr/json")
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
            sys.exit(0)  # 更新成功后退出脚本
    else:
        print("You are using the latest version of the library.")


def get_local_version():
    # 寻找本地 autowsgr 库的 __init__.py 文件并读取版本号
    try:
        with pkg_resources.open_text("autowsgr", "__init__.py") as f:
            for line in f:
                if line.startswith("__version__"):
                    local_version = line.split("=")[1].strip().strip('"')
                    return local_version
            else:
                print("Error: Cannot find __version__ in __init__.py.")
                return
    except Exception as e:
        print(f"Error: {e}")
        return


def update_library():
    subprocess.run(["pip", "install", "--upgrade", "autowsgr"])


# if __name__ == "__main__":
#    check_for_updates()
