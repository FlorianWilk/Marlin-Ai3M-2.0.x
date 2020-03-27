#!/usr/bin/python3
# -*- coding: utf-8 -*-
import traceback
import json
import threading
import sys
import signal
import time
from octorest import OctoRest
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import asyncio
import websocket

ask = False
host="http://printerpi.local:5000"

def convertMillis(millis):
    if millis is None:
        return "unknown"
    seconds=round(int((millis)%60),2)
    minutes=round(int((millis/(60))%60),2)
    hours=round(int((millis/(60*60))%24),2)
    s=""
    u=None
    if hours>0: 
        s=s+'{:02d}:'.format(hours)
        u="h"
    if minutes>0:
        s='{}{:02d}:'.format(s,minutes)
        if u is None:
            u="m"
    if u is None:
        u="s"
    s='{}{:02d}'.format(s,seconds)
    return s+u


class MyButton(QPushButton):
     def __init__(self,*args, **kwargs):
          super().__init__(*args, **kwargs)
          self.setSizePolicy(QSizePolicy(QSizePolicy.Preferred,QSizePolicy.Expanding))
#          self.setMinimumWidth(200)
          self.setAutoFillBackground(False)

#  - PLA/PETG/TPU
#  - Stop
#  - Pause / Resume
#  - HOME
#  - Eject / Present
#  - Filament Change -> Hot -> Retract -> Wait -> Extrude -> Cold
#  - Show Bed Levels


class MyMainButtons(QWidget):

     clicked = pyqtSignal(int)

     def do_home(self):
          self.clicked.emit(0)
     def do_stop(self):
          self.clicked.emit(1)
     def do_pause(self):
          self.clicked.emit(2)
     def do_change(self):
          self.clicked.emit(3)
     def do_calib(self):
          self.clicked.emit(4)

          
     def __init__(self,*args, **kwargs):
          super().__init__(*args, **kwargs)
          layout_buttons=QVBoxLayout()
          layout_buttons.setSpacing(0)
          layout_buttons.setContentsMargins(0,0,0,0)  
#          self.setMinimumWidth(200)
          self.btn_stop=MyButton("Stop")
          self.btn_stop.setObjectName("stop")
          self.btn_stop.setEnabled(False)
          self.btn_stop.clicked.connect(self.do_stop)
          layout_buttons.addWidget(self.btn_stop)          

          self.btn_pause=MyButton("Pause")
          self.btn_pause.setEnabled(False)
          self.btn_pause.clicked.connect(self.do_pause)
          layout_buttons.addWidget(self.btn_pause)          

          self.btn_home=MyButton("Home")
          self.btn_home.clicked.connect(self.do_home)
          layout_buttons.addWidget(self.btn_home)          

          self.btn_change=MyButton("Change")
          self.btn_change.clicked.connect(self.do_change)
          layout_buttons.addWidget(self.btn_change)          

          self.btn_calibrate=MyButton("Calibrate")
          self.btn_calibrate.clicked.connect(self.do_calib)
          layout_buttons.addWidget(self.btn_calibrate)          

          self.setLayout(layout_buttons)

     def setStates(self,states):
          self.states=states

class MyTemps(QWidget):

     def __init__(self,*args,**kwargs):
          super().__init__(*args, **kwargs)
          #self.setSizePolicy(QSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding))

          layout=QHBoxLayout()
          layout.setSpacing(0)
          layout.setContentsMargins(0,0,0,0)          
          self.setMaximumHeight(150)
          self.setLayout(layout)
          self.hotend_label=QLabel("0°")
          self.hotend_label.setObjectName("hotend_temp")
          self.hotend_label.setSizePolicy(QSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding))

          layout.addWidget(self.hotend_label,1)

          self.bed_label=QLabel("0°")
          self.bed_label.setObjectName("bed_temp")
          self.bed_label.setSizePolicy(QSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding))
          layout.addWidget(self.bed_label,1)

     def setTemps(self,temps):
          bed_actual,bed_target=(temps["bed"])
          tool_actual,tool_target=(temps["tool"])
          self.hotend_label.setText(str(tool_actual)+"°")
          self.bed_label.setText(str(bed_actual)+"°")

class MyBigLabel(QLabel):
     pass

class MyPrintContent(QWidget):
     def __init__(self,*args,**kwargs):
          super().__init__(*args, **kwargs)
          layout=QVBoxLayout()
          layout.setSpacing(0)
          layout.setContentsMargins(0,0,0,0)       
          self.setLayout(layout)
          self.setObjectName("print_content")
          
          self.state=MyBigLabel("Printing")
          self.state.setObjectName("state")
          layout.addWidget(self.state)

          self.completion=MyBigLabel("")
          self.completion.setObjectName("completion")
          layout.addWidget(self.completion)

          self.time_left=MyBigLabel("no print time left yet")
          self.time_left.setObjectName("time_left")
          layout.addWidget(self.time_left)


          self.filament_total=MyBigLabel("-")
#          layout.addWidget(self.filament_total)
          layout.addStretch(1)

     def updateUI(self,data):
              #print(data)
              timeleft=convertMillis(data['print_time_left'])+" left"
              filamenttotal=str(int(data['filament_length']/1000))+" m Filament"
              state="Printing - " + convertMillis(data['print_time'])
              completion="{:.0f}% done".format(data["progress_completion"])
              self.state.setText(state)
              self.time_left.setText(timeleft)
              self.filament_total.setText(filamenttotal)
              self.completion.setText(completion)



class MyIdleContent(QWidget):
     def __init__(self,*args,**kwargs):
          super().__init__(*args, **kwargs)

          layout=QVBoxLayout()
          layout.setSpacing(0)
          layout.setContentsMargins(0,0,0,0)            
          self.setLayout(layout)
          self.setObjectName("idle_content")
          idle_label=MyBigLabel("Waiting for Things")
          idle_label.setObjectName("state")
          layout.addWidget(idle_label)

          self.state=MyBigLabel("")
          self.state.setObjectName("last_print")
          self.state.setWordWrap(True)
          layout.addWidget(self.state)

          self.time_total=MyBigLabel("")
          layout.addWidget(self.time_total)

          self.filament_total=MyBigLabel("")
          layout.addWidget(self.filament_total)
          layout.addStretch(1)

     def updateUI(self,data):
          try:
               state= str(data['filename'])
               self.state.setText(state)
               timetotal=convertMillis(data['print_time'])+" total"
               filamenttotal=str(int(data['filament_length']/1000))+" m Filament"
               self.time_total.setText(timetotal)
               self.filament_total.setText(filamenttotal)
          except Exception as ex:
               print(ex)
               self.time_total.setText("No PrintTime available")
               self.filament_total.setText("No Filament was used")          

class MyContent(QWidget):

     def __init__(self,*args,**kwargs):
          super().__init__(*args, **kwargs)

          layout=QVBoxLayout()
          layout.setSpacing(0)
          layout.setContentsMargins(0,0,0,0)            
          self.setLayout(layout)

          label_wilklabs=QLabel("WILK LABS - PrinterControl V0.1 Alpha")
          label_wilklabs.setObjectName("titlebar")
          layout.addWidget(label_wilklabs)

          stack_layout=QStackedWidget()
          self.stack_layout=stack_layout

          self.idle_content=MyIdleContent()
          stack_layout.addWidget(self.idle_content)

          self.print_content=MyPrintContent()
          stack_layout.addWidget(self.print_content)
          
          layout.addWidget(stack_layout)
          self.stack_layout.setCurrentIndex(0)
          self.data=None

     def updateUI(self,data):
          if  not data["state_flags"]['printing']:
               self.stack_layout.setCurrentIndex(0)
          else:
               self.stack_layout.setCurrentIndex(1)
          self.print_content.updateUI(data)
          self.idle_content.updateUI(data)

     def setData(self,data):
          self.data=data
          self.updateUI(self.data)

class PIUI(object):

     def __init__(self):
          self.octo_url=host
          self.octo_key="0bd8c77e808a8e5e3c53ce13696317fa"
          self.client=None
          self.app=None
          self.data={}

          self.content_widget=None
          self.tempt_content=None
          self.main_buttons=None
          self.layout_main=None
          self.client=self.init_client()

          self.data={
               "state_flags":{},
               "state_text":"",
               "bed_temps":"",
               "tool_temps":"",
               "est_print_time":"",
               "filament_length":"",
               "filament_volument":"",
               "filename":"",
               "progress_completion":"",
               "print_time":"",
               "print_time_left":"",

               "temperatures": {"bed":0,"tool":0},
          }


          self.uri = "ws://printerpi.local:5000/sockjs/websocket"
          self.ws = websocket.WebSocketApp(self.uri,
                                        on_message=self.on_message,
                                        on_error=self.on_error,
                                        on_close=self.on_close)
          self.wst = threading.Thread(target=self.ws.run_forever)
          self.wst.daemon = True
          self.wst.start()
          #asyncio.get_event_loop().run_until_complete(self.webrecv())
#          asyncio.get_event_loop().run_forever()
          self.build_ui()

     def on_message(self,msgstr):
          try:
               msg=json.loads(msgstr)
               #print("Message " + msg["current"])
               if not "current" in msg:
                    return
               state=msg['current']['state']
               self.data['state_flags']=state['flags']
               self.data['state_text']=state['text']
               d_temp=msg['current']['temps']
               if len(d_temp)>0:
                    d_temp=d_temp[0]
                    d_temp_bed=d_temp['bed']
                    self.data['bed_temps']= d_temp_bed['actual'], d_temp_bed['target']
                    d_temp_tool=d_temp['tool0']
                    self.data['tool_temps']=d_temp_tool['actual'],d_temp_tool['target']
                    self.data['temperatures']={'bed':self.data['bed_temps'],'tool':self.data['tool_temps'] } 


               # job infos
               d_job=msg['current']['job']
               self.data['est_print_time']=d_job['estimatedPrintTime']
               if d_job and d_job['filament'] and d_job['filament']['tool0']:
                    self.data['filament_length']=d_job['filament']['tool0']['length']
                    self.data['filament_volume']=d_job['filament']['tool0']['volume']
               self.data['filename']=d_job['file']['display']

               self.data['progress_completion']=msg['current']['progress']['completion']
               self.data['print_time']=msg['current']['progress']['printTime']
               self.data['print_time_left']=msg['current']['progress']['printTimeLeft']
               #print(job_info)        
               #print(printer)
               print(self.data)
               self.update_ui()          
          except Exception as ex:

               traceback.print_exc()
               print(ex)
               print(str(ex)+str(sys.exc_info()[-1].tb_lineno))
     def on_error(self,err):
          print("Error " +err)
     def on_close(self):
          print("Close")

     async def webrecv(self):
          async with websockets.connect(self.uri) as websocket:
               while True:
                    greeting = await websocket.recv()
                    print(f"< {greeting}")


     def init_client(self):
          while True:
              try:
                   client = OctoRest(url=self.octo_url, apikey=self.octo_key)
                   return client
              except Exception as ex:
                   print(ex)
                   time.sleep(10)

     def update(self):
          if not self.client:
               return
          try:
#          if True:
              job_info=self.client.job_info()
              printer=self.client.printer()
              # printer infos
              state=printer['state']
              state_flags=state['flags']
              state_text=state['text']
              d_temp=printer['temperature']
              d_temp_bed=d_temp['bed']
              bed_temps= d_temp_bed['actual'], d_temp_bed['target']
              d_temp_tool=d_temp['tool0']
              tool_temps=d_temp_tool['actual'],d_temp_tool['target']

              # job infos
              d_job=job_info['job']
              est_print_time=d_job['estimatedPrintTime']
              filament_length=0
              filament_volume=0
              if d_job and d_job['filament'] and d_job['filament']['tool0']:
                  filament_length=d_job['filament']['tool0']['length']
                  filament_volume=d_job['filament']['tool0']['volume']
              filename=d_job['file']['display']
    
              progress_completion=job_info['progress']['completion']
              progress_print_time=job_info['progress']['printTime']
              progress_print_time_left=job_info['progress']['printTimeLeft']
              #print(job_info)        
              #print(printer)
              self.data={
                   "state_flags":state_flags,
                   "state_text":state_text,
                   "bed_temps":bed_temps,
                   "tool_temps":tool_temps,
                   "est_print_time":est_print_time,
                   "filament_length":filament_length,
                   "filament_volument":filament_volume,
                   "filename":filename,
                   "progress_completion":progress_completion,
                   "print_time":progress_print_time,
                   "print_time_left":progress_print_time_left,

                   "temperatures": {"bed":bed_temps,"tool":tool_temps},
              }
              #print(self.data)
              self.update_ui()
          except Exception as ex:
               print(ex)

     def buttonclicked(self,i):
         try:
             if i==0:
                 self.client.home()
             elif i==1:
                 self.client.cancel()
             if i==2:
                self.client.toggle()
             if i==3:
                self.client.gcode("M109 S190\nG91\nG1 E-550 F4000\nM18 E")
                input("Press Enter to continue...")
                self.client.gcode("G1 E550 F2000\nM104 S0\nG90\nM18")
                



# Changer filament GCode
# M109 S190
# G91
# G1 E-550 F4000
# M18 E
# Keypress
# G1 E550 F2000
# M104 S0
# G90
# M84

             if i==4:
                self.client.gcode("G28")
                print(self.client.gcode("G29"))
             else:
                print("Not implemented yet")
         except:
             print("Error")

     def build_ui(self):
          self.app = QApplication(sys.argv)
          self.app.setOverrideCursor(Qt.BlankCursor)          
          app=self.app
          w = QWidget()
          sshFile="./style.css"
          with open(sshFile,"r") as fh:
               app.setStyleSheet(fh.read())
      
#          w.resize(250, 150)
#          w.move(100, 100)
          w.showFullScreen()
          w.setWindowTitle('OctoPIUI')

          # Left / Right for MainButtons

          layout_main=QHBoxLayout()
          self.layout_main=layout_main
          layout_main.setSpacing(0)
          layout_main.setContentsMargins(0,0,0,0)
          # Layout for Content / Temps
          layout_content=QVBoxLayout()
          layout_content.setSpacing(0)
          layout_content.setContentsMargins(0,0,0,0)

          buttons=MyMainButtons()
          buttons.clicked.connect(self.buttonclicked)
          self.main_buttons=buttons
          layout_main.addLayout(layout_content)
          layout_main.addWidget(buttons)


          main_content=MyContent()
          temp_content=MyTemps()
          self.temp_content=temp_content
          self.main_content=main_content
          layout_content.addWidget(main_content)
          layout_content.addWidget(temp_content)

          w.setLayout(layout_main)
          w.show()

          timer =QTimer()
          timer.timeout.connect(lambda:None)
          timer.start(100)

          update_timer=QTimer()
          update_timer.timeout.connect(self.update)
          #update_timer.start(3000)
          sys.exit(app.exec_())

     def update_ui(self):
          data = self.data
          self.temp_content.setTemps(data["temperatures"])
          self.main_buttons.setStates(data["state_flags"])
          self.main_content.setData(data)

def sigint_handler(*args):
     sys.stderr.write('\r')
     if ask and QMessageBox.question(None, '', "Are you sure you want to quit?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
        QApplication.quit()
     else:
        QApplication.quit()

if __name__ == '__main__':
     signal.signal(signal.SIGINT, sigint_handler)     
     piui=PIUI()

