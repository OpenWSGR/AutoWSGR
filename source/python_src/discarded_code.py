
from supports import *
from fight import *
from game import *
from api import *

def qxhd(timer:Timer):
    click(timer, 500, 500, delay=.25)
    click(timer, 600, 420, delay=0)
    wait_pages(timer, 'fight_prepare_page')
    time.sleep(.25)
    click(timer, 900, 500)
    time.sleep(3)
    click(timer, 900, 500, delay=0)
    wait_until_decision(timer)
    fight(timer, 'fight', DecisionBlock(formation=4))
    time.sleep(4)
    click(timer, 30, 30, delay=.25)
    click(timer, 370, 300, delay=1.25)
