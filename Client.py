from tkinter import *
import tkinter.messagebox
from PIL import Image, ImageTk
import socket
import threading
import sys
import traceback
import os
import time

from RtpPacket import RtpPacket

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"


class Client:
    INIT = 0
    READY = 1
    PLAYING = 2
    DESCRIBE = 3
    state = INIT

    SETUP = 'SETUP'
    PLAY = 'PLAY'
    PAUSE = 'PAUSE'
    TEARDOWN = 'TEARDOWN'
    DESCRIBE_STR = 'DESCRIBE'

    RTSP_VER = "RTSP/1.0"
    TRANSPORT = "RTP/UDP"

    # Initiation..
    def __init__(self, master, serveraddr, serverport, rtpport, filename):
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self.handler)
        self.createWidgets()
        self.serverAddr = serveraddr
        self.serverPort = int(serverport)
        self.rtpPort = int(rtpport)
        self.fileName = filename
        self.rtspSeq = 0
        self.sessionId = 0
        self.requestSent = -1
        self.teardownAcked = 0
        self.connectToServer()
        self.frameNbr = 0
        self.shutDown = threading.Event()
        self.shutDown.clear()
        self.lock = threading.Event()
        self.lock.clear()
        self.stopRtp = threading.Event()
        self.stopRtp.clear()

        # New for calculate the statistics
        self.numLostFrame = 0
        self.sumOfTime = 0
        self.sumData = 0
        self.stop = True
        self.begin = 0
        self.setupMovie()

    # THIS GUI IS JUST FOR REFERENCE ONLY, STUDENTS HAVE TO CREATE THEIR OWN GUI
    def createWidgets(self):
        """Build GUI."""
        # Create Setup button
        # self.setup = Button(self.master, width=20, padx=3, pady=3)
        # self.setup["text"] = "Setup"
        # self.setup["command"] = self.setupMovie
        # self.setup.grid(row=1, column=0, padx=2, pady=2)

        # Create Play button
        self.start = Button(self.master, width=20, padx=3, pady=3)
        self.start["text"] = "Play"
        self.start["bg"] = "#34BE82"
        self.start["command"] = self.playMovie
        self.start.grid(row=1, column=0, padx=2, pady=2)

        # Create Pause button
        self.pause = Button(self.master, width=20, padx=3, pady=3)
        self.pause["text"] = "Pause"
        self.pause["bg"] = "#FBFF00"
        self.pause["command"] = self.pauseMovie
        self.pause.grid(row=1, column=1, padx=2, pady=2)

        # Create Teardown button
        self.teardown = Button(self.master, width=20, padx=3, pady=3)
        self.teardown["text"] = "Teardown"
        self.teardown["bg"] = "red"
        self.teardown["command"] = self.exitClient
        self.teardown.grid(row=1, column=2, padx=2, pady=2)

        # Create a label to display the movie
        self.label = Label(self.master, height=19)
        self.label.grid(row=0, column=0, columnspan=4,
                        sticky=W+E+N+S, padx=5, pady=5)
        # Create describe button
        self.describe = Button(self.master, width=20, padx=3, pady=3)
        self.describe["text"] = "Describe"
        self.describe["bg"] = "blue"
        self.describe["command"] = self.describeVideo
        self.describe.grid(row=1, column=3, padx=2, pady=2)

    def setupMovie(self):
        """Setup button handler."""
        if self.state == self.INIT:
            # Listen to RTSP reply
            self.tearDown = threading.Event()
            self.tearDown.clear()
            threading.Thread(target=self.recvRtspReply).start()
            self.sendRtspRequest(self.SETUP)

    def exitClient(self):
        """Teardown button handler."""
        if self.state != self.INIT:
            self.sendRtspRequest(self.TEARDOWN)
        os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT)

        # Calculate
        rate = float(self.numLostFrame) / float(self.frameNbr)
        print('\nThe amount of package loss: ' + str(self.numLostFrame))
        print('Frame amount: ' + str(self.frameNbr))
        print('Packet loss rate: ' + str(rate) + '%')

        if not self.stop:
            self.sumOfTime += time.time() - self.begin

        rateData = float(int(self.sumData)/int(self.sumOfTime))
        print('Video Data Rate: ' + str(rateData) + ' Bytes per second\n')

    def pauseMovie(self):
        """Pause button handler."""
        if self.state == self.PLAYING:
            self.sendRtspRequest(self.PAUSE)

    def playMovie(self):
        if self.state == self.INIT:
            self.sendRtspRequest(self.SETUP)
            return
        """Play button handler."""
        if self.state == self.READY:
            self.playEvent = threading.Event()
            self.playEvent.clear()
            threading.Thread(target=self.listenRtp).start()
            self.sendRtspRequest(self.PLAY)

    # New function describe
    def describeVideo(self):
        self.sendRtspRequest(self.DESCRIBE)

    def listenRtp(self):
        """Listen for RTP packets."""
        print('Start receiving RTP packet\n')
        self.begin = time.time()
        self.stop = False
        while True:
            try:
                data = self.rtpSocket.recv(20480)
                if data:
                    rtpPacket = RtpPacket()
                    rtpPacket.decode(data)
                    self.sumData += len(data)

                    currFrameNbr = rtpPacket.seqNum()

                    if currFrameNbr > self.frameNbr:
                        # Calculate lost frame
                        self.numLostFrame += (currFrameNbr - self.frameNbr - 1)
                        self.frameNbr = currFrameNbr
                        self.updateMovie(self.writeFrame(
                            rtpPacket.getPayload()))

            except:
                self.sumOfTime += time.time() - self.begin
                self.stop = True

                if self.playEvent.isSet() or self.tearDown.isSet() or self.shutDown.isSet():
                    print('Stop receiving RTP packet\n')
                    break
        self.stopRtp.set()
        self.sumOfTime += time.time() - self.begin
        self.stop = True

    def writeFrame(self, data):
        """Write the received frame to a temp image file. Return the image file."""
        filename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
        file = open(filename, "wb")
        file.write(data)
        file.close()
        return filename

    def updateMovie(self, imageFile):
        """Update the image file as video frame in the GUI."""
        photo = ImageTk.PhotoImage(Image.open(imageFile))
        self.label.configure(image=photo, height=300)
        self.label.image = photo

    def connectToServer(self):
        self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        """Connect to the Server. Start a new RTSP/TCP session."""
        try:
            self.rtspSocket.connect((self.serverAddr, self.serverPort))
            print('Connected to server\n')
        except:
            print('Cannot connect to server\n')

    def sendRtspRequest(self, requestCode):
        """Send RTSP request to the server."""
        # -------------
        # TO COMPLETE
        # -------------
        if requestCode == self.SETUP and self.state == self.INIT:

            self.rtspSeq += 1

            request = requestCode + ' ' + self.fileName + ' RTSP/1.0\nCSeq: ' + \
                str(self.rtspSeq) + '\n' + \
                'Transport: RTP/UDP; client_port= ' + str(self.rtpPort)

            self.requestSent = self.SETUP

        elif requestCode == self.PLAY and self.state == self.READY:

            self.rtspSeq += 1

            request = requestCode + ' ' + self.fileName + ' RTSP/1.0\nCSeq: ' + \
                str(self.rtspSeq) + '\n' + 'Session: ' + str(self.sessionId)

            self.requestSent = self.PLAY

        elif requestCode == self.PAUSE and self.state == self.PLAYING:
            # Update RTSP sequence number
            self.rtspSeq += 1
            request = requestCode + ' ' + self.fileName + ' RTSP/1.0\nCSeq: ' + \
                str(self.rtspSeq) + '\n' + 'Session: ' + str(self.sessionId)
            # Keep track of sent request
            self.requestSent = self.PAUSE

        elif requestCode == self.TEARDOWN and not self.state == self.INIT:

            self.rtspSeq += 1

            request = requestCode + ' ' + self.fileName + ' RTSP/1.0\nCSeq: ' + \
                str(self.rtspSeq) + '\n' + 'Session: ' + str(self.sessionId)

            self.requestSent = self.TEARDOWN
        elif requestCode == self.DESCRIBE and self.state == self.READY:
            request = "%s %s %s" % (
                self.DESCRIBE_STR, self.fileName, self.RTSP_VER)
            request += "\nCSeq: %d" % self.rtspSeq
            request += "\nSession: %d" % self.sessionId
        else:
            return

        print(request)

        self.rtspSocket.send(request.encode())

    def recvRtspReply(self):
        """Receive RTSP reply from the server."""
        print('Start receiving RTSP reply\n')
        while True:
            try:
                data = self.rtspSocket.recv(1024)
                if data:
                    self.parseRtspReply(data.decode("utf-8"))
                if self.shutDown.isSet() or self.tearDown.isSet():
                    print('Stop receiving RTSP reply\n')
                    self.rtspSocket.shutdown(socket.SHUT_RDWR)
                    self.rtspSocket.close()
                    if self.tearDown.isSet():
                        self.connectToServer()
                    break
            except:
                pass

    def parseRtspReply(self, data):
        """Parse the RTSP reply from the server."""
        reply = data.split('\n')
        seq = int(reply[1].split(' ')[1])

        if seq == self.rtspSeq:
            session = int(reply[2].split(' ')[1])

            if self.sessionId == 0:
                self.sessionId = session

            if self.sessionId == session:
                if self.requestSent == self.SETUP:
                    print("Here")
                    self.openRtpPort()

                elif self.requestSent == self.PLAY:
                    self.playEvent.clear()
                    self.state = self.PLAYING

                elif self.requestSent == self.PAUSE:
                    self.playEvent.set()
                    self.state = self.READY

                elif self.requestSent == self.TEARDOWN:
                    self.state = self.INIT
                    self.tearDown.set()
                    self.stopRtp.wait()
                    self.stopRtp.clear()

                    os.remove(CACHE_FILE_NAME +
                              str(self.sessionId) + CACHE_FILE_EXT)
                    self.frameNbr = 0
                    self.sessionId = 0

                print(data + '\n')

            else:
                print('Unmatch SessionID')

    def openRtpPort(self):
        """Open RTP socket binded to a specified port."""
        # -------------
        # TO COMPLETE
        # -------------
        # Create a new datagram socket to receive RTP packets from the server
        self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rtpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Set the timeout value of the socket to 0.5sec
        self.rtpSocket.settimeout(0.5)

        try:
            self.rtpSocket.bind(('localhost', self.rtpPort))
            self.state = self.READY
            print("Binded RTP socket to port " + str(self.rtpPort))
        except:
            print("Cannot bind to port " + str(self.rtpPort))

    def handler(self):
        """Handler on explicitly closing the GUI window."""
        self.pauseMovie()
        if tkinter.messagebox.askokcancel("Quit?", "Are you sure you want to quit?"):
            self.shutDown.set()
            self.sendRtspRequest(self.TEARDOWN)
            self.rtspSocket.shutdown(socket.SHUT_RDWR)
            self.rtspSocket.close()
            self.master.destroy()
            self.master.quit()
        else:  # When the user presses cancel, resume playing.
            self.playMovie()
