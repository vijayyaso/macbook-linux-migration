import sys, time
from evdev import UInput, ecodes as e, AbsInfo
SYNC_FIX = len(sys.argv) > 1 and sys.argv[1] == 'fix'
cap = {e.EV_KEY: [e.BTN_TOUCH, e.BTN_TOOL_FINGER, e.BTN_TOOL_DOUBLETAP, e.BTN_LEFT],
       e.EV_ABS: [(e.ABS_X, AbsInfo(0,-5000,5000,0,0,97)), (e.ABS_Y, AbsInfo(0,-5000,5000,0,0,97)),
                  (e.ABS_MT_SLOT, AbsInfo(0,0,4,0,0,0)),
                  (e.ABS_MT_TRACKING_ID, AbsInfo(0,0,65535,0,0,0)),
                  (e.ABS_MT_POSITION_X, AbsInfo(0,-5000,5000,0,0,97)),
                  (e.ABS_MT_POSITION_Y, AbsInfo(0,-5000,5000,0,0,97))]}
NAME = 'slot-test-fix' if SYNC_FIX else 'slot-test-raw'
ui = UInput(cap, name=NAME, vendor=0x5ac, product=0x273)
time.sleep(0.5)
time.sleep(1.5)
def w(*ev):
    for t,c,v in ev: ui.write(t,c,v)
    ui.syn(); time.sleep(0.02)
S,I,X,Y = e.ABS_MT_SLOT, e.ABS_MT_TRACKING_ID, e.ABS_MT_POSITION_X, e.ABS_MT_POSITION_Y
A = e.EV_ABS
# resync-style frame: clone ends with current slot = 1
w((A,S,0),(A,I,1),(A,X,100),(A,Y,100),(A,S,1),(A,I,2),(A,X,900),(A,Y,100),(e.EV_KEY,e.BTN_TOUCH,1),(e.EV_KEY,e.BTN_TOOL_DOUBLETAP,1))
# kernel's current slot was 0 -> kernel omits the SLOT event on its next frame
pre = [(A,S,0)] if SYNC_FIX else []
w(*pre,(A,I,-1))                     # finger 0 lifts (kernel: no SLOT event)
w((A,S,1),(A,I,-1),(e.EV_KEY,e.BTN_TOUCH,0),(e.EV_KEY,e.BTN_TOOL_DOUBLETAP,0))  # finger 1 lifts
time.sleep(0.2)
w((A,S,0),(A,I,5),(A,X,300),(A,Y,300),(e.EV_KEY,e.BTN_TOUCH,1),(e.EV_KEY,e.BTN_TOOL_FINGER,1))  # new finger
time.sleep(0.4)
print('MODE:', NAME)
ui.close()
