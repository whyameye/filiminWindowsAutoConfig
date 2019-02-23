"""
Filimin AutoConfig
Autoconfigure Filimin for Windows Machines
v0.1.4 May 8, 2017
John Harrison
"""

import autoConfigUi as ui
from PyQt4 import QtCore, QtGui
import sys, subprocess, time, tempfile, urllib, urllib2, os
import icons_rc
import traceback

secsForFiliminSSID = 30

#************************************************************************
# CLASS FOR CONTROLLER
#************************************************************************


class Worker(QtCore.QThread):
    showDialog = QtCore.pyqtSignal(object)
    exception = QtCore.pyqtSignal(object)
    success = QtCore.pyqtSignal(object)
    updateEventSlot = QtCore.pyqtSignal(object)
    retrySlot = QtCore.pyqtSignal(object)
    killSlot = QtCore.pyqtSignal(object)
    step = 0
    connectedToHomeWiFi = True
    credentials = False
    alreadyFailed = False
    
    def __init__(self, parent = None):
        self.thread = QtCore.QThread.__init__(self, parent)
        # self.exiting = False # not sure what this line is for
        print "worker thread initializing"
        sys.excepthook = self.excepthook # FIXME
        self.owner = parent

    def run(self):
        self.initUi()
        self.retrySlot.connect(self.retry)
        self.giveIntroToUser(self.run,self.fail)
        print "worker thread running"
        self.dialogWindow = True
        while self.dialogWindow:
            time.sleep(1)
        credentials = self.getWiFiCredentials()
        self.credentials = credentials # bad hack so we have the info if we call fail
        print "credentials: "+credentials[0]+" "+credentials[1]
        ssid = self.getFiliminSSID()
        profile = self.createAndLoadProfile(ssid)
        confirmed = False
        self.connectedToHomeWiFi = False
        tries = 1
        while not confirmed and tries < 3:
            print "Confirming: "+str(tries)
            self.connectToFilimin(ssid)
            confirmed = self.readAndWriteToFilimin(credentials, tries)
            tries += 1
        self.connectBackToWiFi(credentials, confirmed)
        self.connectedToHomeWiFi = True
        self.finishUp(confirmed)
        # getattr(self, self.steps[self.step])(self.steps[self.step+1],
        #                                     self.steps[len(self.steps)-1])

    def __del__(self):
        print "worker thread dieing"

    def excepthook(self, excType, excValue, tracebackobj):
        """
        Global function to catch unhandled exceptions.

        @param excType exception type
        @param excValue exception value
        @param tracebackobj traceback object
        """
        theError = str(excType)+"\n"+str(excValue)+"\n"+str(traceback.format_tb(tracebackobj))
        mailBody = urllib.urlencode({'subject':'Oops. The autoconfig just blew up','body':'The Filimin Autoconfiguration app just conked out and said this:\n\n'+theError})
        notice = "<center><h2>Unexpected Error</h2><br /><br />Filimin Autoconfigure has encountered an unexpected error. Please <a href='mailto:errorReports@filimin.com?&"+mailBody+"'>report the information below</a> so we may refer to it if you wish to <a href='https://filimin.com/contact'>followup with us.</a></center><br /<br />"
        msg = str(notice)+"<i>"+theError+"</i>"
        self.exception.emit(msg) # if uncommented prevents fail signal?

    toHex = lambda self,x:"".join([hex(ord(c))[2:].zfill(2) for c in x])

    def fail(self, str):
        if self.credentials and not self.connectedToHomeWiFi and not self.alreadyFailed:
            self.alreadyFailed = True
            print "Well that was a bust. Connecting back to home Wi-Fi."
            self.connectBackToWiFi(self.credentials, False)
        mailBody = urllib.urlencode({'subject':'AutoConfig Error: '+str,'body':'Autoconfig has encountered the following error:\n\n'+str})
        msg = "<center><h2>Autoconfiguration Error</h2>"+str+"<i><br /><br />You may be able to find more information about this error in our <a href='https://filimin.com/autoConfigurationProblems'>Autoconfiguration Troubleshooting section.</a><br /><br />You can also <a href='mailto:errorReports@filimin.com?&"+mailBody+"'>report this error</a> so we may refer to it if you wish to <a href='https://filimin.com/contact'>followup with us.</a></i></center>"
        self.updateEventSlot.emit({'state':'failure'})
        self.exception.emit(msg)
        while True:
            time.sleep(1)

    def retry(self):
        subprocess.Popen([os.path.abspath(str(sys.argv[0]))])
        self.killSlot.emit({})
        return
        
    def executeCmd(self, cmd):
        result = subprocess.check_output(cmd, universal_newlines=True, shell=True, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        result = result.split('\n')
        return result

    def findInList(self, needle, haystack, start=0):
        cnt = 0
        for i in haystack:
            if needle in i and cnt >= start:
                return cnt
            cnt += 1
        return -1

    def initUi(self):
        self.updateEventSlot.emit({'step':0, 'state':'blank'})
        
    def giveIntroToUser(self,success,failure):
        self.showDialog.emit([success,failure])
        
    def getWiFiProfile(self):
        try:
            result = self.executeCmd(["netsh","wlan", "show", "interfaces"])
        except:
            self.fail("The standard Windows Wi-Fi configuration service is not available. Either you do not have Wi-Fi on this device or your Wi-Fi is maintained with non-standard WiFi software. You can either try this autoconfig software on another Wi-Fi enabled Windows device or you can visit http://filimin.com/setupFilimin on any WiFi-enabled laptop, phone or tablet to configure your Filimin's WiFi settings manually.")
        if self.findInList('There is 1 interface', result) == -1:
            self.fail("Did not find a unique WiFi device. You can either try this autoconfig software on another Wi-Fi enabled Windows device or you can visit http://filimin.com/setupFilimin on any WiFi-enabled laptop, phone or tablet to configure your Filimin's WiFi settings manually.")
        state = self.findInList('State', result)
        if state == -1:
            self.fail("Could not find state of WiFi interface. Is your WiFi on this device enabled?")
        connected = ("connected" in result[state])
        if connected != True:
            self.fail("WiFi Interface appears to not be connected. Connect this device to your WiFi and try again.")
        if self.findInList('SSID                   : Filimin_', result) != -1:
            self.fail("This device is connected to a Filimin. Connect to the your router (the Internet) instead and try again.")
        c = self.findInList('Channel', result)
        try:
            channel = result[c][result[c].index(':')+2:] # NEED TRY/CATCH HERE
            channel = int(channel)
        except:
            self.fail("Your Wi-Fi is not on or is not connected to the Internet. Turn on the Wi-Fi and confirm your Internet is working on this device. Then try again.")
        if channel > 14:
            self.fail("It appears this Windows device is connected to a 5Ghz channel. Filimins support only 2.4Ghz channels.\nReconnect this device to a 2.4Ghz channel and try again.")
        r = self.findInList('Authentication', result)
        authType = result[r][result[r].index(':')+2:]
        aTypes = ['WPA2-Personal', 'Open', 'WPA-Personal', 'WEP']
        match = False
        for aType in aTypes:
            if authType == aType:
                match = True
        if not match:
            self.fail("Authentication "+authType+" not supported by Filimin. Supported types: WPA2-Personal, Open, WPA-Personal, WEP")
        profile = self.findInList('Profile                :', result)
        if profile == -1:
            self.fail("Could not find profile")
        profileName = result[profile][result[profile].index(':')+2:-1]
        return profileName

    def getSSIDAndPw(self, profile):
        try:
            result = self.executeCmd(["netsh","wlan", "show", "profile", "name="+profile, "key=clear"])
        except:
            self.fail("Net shell unable to show profile.<br />This autoconfig will not work on this device.")
        nameLine = self.findInList('SSID name', result)
        if nameLine == -1:
            self.fail("Could not find SSID in profile")
        ssid = result[nameLine][result[nameLine].index('"')+1:-1]
        keyLine = self.findInList('Security key', result)
        keyStatus = result[keyLine][result[keyLine].index(':')+2:]
        if keyStatus == "Absent":
            pw = ''
        else:
            pwLine = self.findInList('Key Content', result)
            if pwLine == -1:
                self.fail("Permissions Error: Cannot read Wi-Fi password. Please abort this app and re-run as an Administrator.")
            else:
                pw = result[pwLine][result[pwLine].index(':')+2:]
        return [ssid, pw]
    
    def getWiFiCredentials(self):
        print "wifi credentials"
        self.updateEventSlot.emit({'step':1, 'state':'spinning'})
        time.sleep(3) # seems like if we try to see the Filimin too quickly after unplug/replug it's bad?
        profile = self.getWiFiProfile()
        print "Profile: "+profile
        result = self.getSSIDAndPw(profile)
        ssid = result[0]
        pw = result [1]
        result.append(profile)
        print "SSID: "+ssid
        print "PW: "+pw
        return result

    def getFiliminSSID(self):
        try:
            WiFiInterface = self.executeCmd(["netsh","wlan", "show", "networks"])[1][17:-1].split(' ')
        except:
            self.fail("Network shell call to show networks failed.<br />This autoconfig app is not compatible with this device.")
        sys.stdout.write('"Wi-Fi Interface name: "')
        print WiFiInterface
        WiFiInterface[0] = 'name="'+WiFiInterface[0]
        WiFiInterface[-1] = WiFiInterface[-1]+'"'
        print "turning off network to delete cache"
        try:
            self.executeCmd(["netsh","interface", "set", "interface"]+WiFiInterface+["admin=disabled"])
        except:
            self.fail("Network shell call to temporarily disable interface failed.<br />This autoconfig app is not compatible with this device.")
        print "turning on network"
        try:
            self.executeCmd(["netsh","interface", "set", "interface"]+WiFiInterface+["admin=enabled"])
        except:
            self.fail("Network shell call to re-enable (reset) interface failed.<br />This autoconfig app is not compatible with this device.")
        tries = 0
        while tries < secsForFiliminSSID:
            print ".",
            fails = 0
            succeeded = False
            while not succeeded:
                if fails > 10:
                    self.fail("Network shell call to show the networks failed.<br />This autoconfig app is not compatible with this device.")
                try:
                    result = self.executeCmd(["netsh","wlan", "show", "networks"])
                    succeeded = True
                except:
                    fails += 1
                    print "Net Shell has failed "+str(fails)+" times"
                    time.sleep(1)
                    tries += 1
            line = self.findInList("Filimin",result)
            if line != -1:
                break
            tries += 1
            time.sleep(1)
        print
        if tries >= secsForFiliminSSID:
            self.fail("Filimin not found. Is it plugged in? Unplug and replug your Filimin and try again.")
        filiminSSID = result[line][result[line].index("Filimin"):]
        print "Filimin SSID: >>>"+filiminSSID+"<<<"
        return filiminSSID
    
    def createAndLoadProfile(self, ssid):
        self.updateEventSlot.emit({'step':2, 'state':'spinning'})
        write = True
        hex = self.toHex(ssid)
        if getattr( sys, 'frozen', False ):
            basePath = sys._MEIPASS+"/"
        else:
            basePath = ''
        print "basePath:" +basePath
        fTemplate = open(basePath+'template.xml', 'r')
        fOut = tempfile.NamedTemporaryFile(suffix=".xml",delete=False)
        print 'temp file: '+fOut.name
        for line in fTemplate:
            if '<SSIDConfig>' in line:
                write = False
                fOut.write('<SSIDConfig>\n<SSID>\n<hex>'+hex+'</hex>\n<name>'+ssid+'</name>\n</SSID>\n</SSIDConfig>\n')
            elif '<name>' in line and write == True:
                fOut.write("<name>"+ssid+"</name>\n")
            elif '</SSIDConfig>' in line:
                write = True
            else:
                if write:
                    fOut.write(line)
        fOut.close()
        fTemplate.close()
        try:
            self.executeCmd(["netsh","wlan", "add", "profile", "filename="+fOut.name])
        except:
            self.fail("Net shell failed to add profile.<br />This autoconfiguration app is not compatible with this device. Please use another device or use the Filimin online setup.")
            
    def connectToNetwork(self, targetssid, profile, errorMsg):
        tries = 0
        while tries < 5:
            tries += 1
            try:
                result = self.executeCmd(["netsh","wlan", "connect", "name="+profile])
            except:
                self.fail("Failed to connect to profile.<br />This autoconfiguration app is probably incompatible with this device. Please use another device or use the Filimin online setup.")
            t2 = 0
            state = -1
            while t2 < secsForFiliminSSID:
                time.sleep(1)
                result = self.executeCmd(["netsh","wlan", "show", "interfaces"])
                state = self.findInList("State                  : connected",result)
                if state != -1:
                    break;
                t2 += 1
            if state == -1:
                self.fail("Wi-Fi interface never connected.\n\nThis error is typically resolved on a second try.")
            ssidLine = self.findInList("SSID", result)
            ssid = result[ssidLine][result[ssidLine].index(':')+2:]
            print "connected to SSID >>>"+ssid+"<<<"
            if ssid == targetssid:
                break
            print "connected to wrong network. Trying again..."
            time.sleep(1)
        if (ssid != targetssid):
            self.fail(errorMsg)
            
    def connectToFilimin(self,filiminName):
        self.updateEventSlot.emit({'step':3, 'state':'spinning'})
        self.connectToNetwork(filiminName, filiminName, "Cannot connect to Filimin")

    def getValue(self, key, haystack):
        start = haystack.index(key)+len(key)
        start = haystack.index(':',start)+1
        if haystack[start] == ' ':
            start += 1
        try:
            result = haystack[start:haystack.index(',',start)]
        except:
            result = haystack[start:haystack.index('}',start)]
        return result
    
    def readAndWriteToFilimin(self, credentials, tries):
        self.updateEventSlot.emit({'step':4, 'state':'spinning'})
        name = credentials[0]
        pw = credentials[1]
        try:
            inData = urllib2.urlopen('http://192.168.4.1/sendDataFromFilimin')
            print "reading from Filimin"
            data = inData.read()
        except:
            return False
        print data
        dStart =  data.index('connectedToSSID')+20
        currentSSID = data[dStart:data.index('"',dStart)]
        print "Filimin Current SSID: "+currentSSID
        confirmed = False
        self.updateEventSlot.emit({'step':5, 'state':'spinning'})
        if currentSSID == name and tries > 1:
            print "Confirmed after try: "+str(tries)
            confirmed = True
        time.sleep(1)
        oldData = data
        data = {"startColor" : self.getValue("startColor",oldData),
                "endColor" : self.getValue("endColor",oldData),
                "limitColors" : self.getValue("limitColors",oldData),
                "timeOffset" : self.getValue("timeOffset",oldData),
                "silentTimeStart" : self.getValue("silentTimeStart",oldData),
                "silentTimeEnd" : self.getValue("silentTimeEnd",oldData),
                "silentTimeEnabled" : self.getValue("silentTimeEnabled",oldData),
                "fadeTime" : self.getValue("fadeTime",oldData),}

        # data = {}
        data['ssid'] = name
        data['pw'] = pw
        data = urllib.urlencode(data)
        print "writing to Filimin: "+ data
        try:
            req = urllib2.Request('http://192.168.4.1/receiveDataToFilimin', data)
            response = urllib2.urlopen(req, timeout=10)
            filiminResponse = response.read()
            print "response: "+filiminResponse
            if filiminResponse == '{ "saved" : true }':
                print "response confirmed!"
                return True
            return False
            return confirmed
        except:
            print "Error"
            return False
            return confirmed

    def connectBackToWiFi(self, credentials, confirmed):
        if confirmed:
            self.updateEventSlot.emit({'step':6, 'state':'spinning'})
        ssid= credentials[0]
        profile = credentials[2]
        self.connectToNetwork(ssid, profile, "Cannot connect back to Wi-Fi")
        
    def finishUp(self, confirmed):
        if confirmed:
            self.success.emit("<h2><center><b>Configuration succeeded!</b></center></h2><br /><br />Your Filimin will now restart to connect to your Wi-Fi.<br /><br />After it successfully connects, you should see a <i>celebratory rainbow</i> before it goes dark or shows a solid color.<br /><br />When the bootup completes, confirm you are connected by touching the shade with your entire hand. You should see it react to your touch by changing between solid colors.<br /><br />Problems? Refer to our <a href='https://filimin.com/autoConfigurationProblems'>Autoconfiguration Troubleshooting section.</a><br />Or if you prefer a human we're always <a href='https://filimin.com/contact'>glad to help.</a>")
            self.updateEventSlot.emit({'step':6, 'state':'complete'})
        else:
            self.step = 5
            self.fail("Could not confirm settings from your Filimin. It may not have configured correctly. Perhaps try again?")
        print "job done"
        
#************************************************************************
# MAKE IT ALL HAPPEN
#************************************************************************

    
if __name__ == "__main__":

    app = QtGui.QApplication(sys.argv)
    MyApp = ui.MyWindow(child=Worker)
    sys.exit(app.exec_())

