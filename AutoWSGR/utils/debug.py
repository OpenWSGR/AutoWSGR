
def print_err(error, ex_info=""):
    print("\n===================ERROR===================\n")
    print(error)
    print("Extra infomation:",ex_info)
    print("\n====================END====================")
    
    
def print_war(warning, ex_info=""):
    print("\n===================WARNING===================\n")
    print(warning)
    print("Extra infomation:",ex_info)
    print("\n====================END====================")
    
def print_debug(condition, *args):
    if(condition):
        print(*args)
    
    