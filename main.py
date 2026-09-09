"""
刷题软件 - 程序入口
"""

from menu import main_loop


def main():
    """程序启动函数"""
    print("欢迎使用刷题软件！")
    print("输入 exit 可随时返回主菜单或退出程序。")
    main_loop()


if __name__ == "__main__":
    main()
