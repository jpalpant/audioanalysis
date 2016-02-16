'''
Created on Nov 16, 2015

@author: justinpalpant

Copyright 2015 Justin Palpant

This file is part of the Jarvis Lab Audio Analysis program.

Audio Analysis is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

Audio Analysis is distributed in the hope that it will be useful, but WITHOUT 
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS 
FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
Audio Analysis. If not, see http://www.gnu.org/licenses/.
'''

import sys, os, time, fnmatch

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt4agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT)
from matplotlib.backend_bases import cursors

from PyQt4 import QtGui, QtCore
from PyQt4.uic import loadUiType

import numpy as np
import logging, pyaudio

import datetime
import collections

from freqanalysis import AudioAnalyzer, SongFile
from threadsafety import BGThread, SignalStream


#Determine if the program is executing in a bundle or not
uifile = os.path.join(os.path.dirname(__file__), 'main.ui')
Ui_MainWindow, QMainWindow = loadUiType(uifile)

#decorator for asynchronous class functions
def async_gui_call(fn):
    def new_fn(self, *calling_args, **calling_kwargs):
        self.set_signals_busy()
        thread_fun = lambda: fn(self, *calling_args, **calling_kwargs)
        fnname = fn.func_name
        t = BGThread(thread_fun, name=fnname)
        t.finished.connect(lambda *a: self.async_call_cleanup(fnname))
        self.threads.append(t)
        t.start()
    
    return new_fn

class AudioGUI(Ui_MainWindow, QMainWindow):
    """The GUI for automatically identifying motifs
    
    
    """
    
    logger = logging.getLogger('JLAA')
        
    def __init__(self):
        """Create a new AudioGUI
        
        
        """
        #Initialization of GUI from Qt Designer
        super(AudioGUI, self).__init__()
        self.setupUi(self)
                        
        #Initialize text output to GUI
        self.printerbox = OutLog(self.console, interval_ms=250)
        self.printstream = SignalStream(interval_ms=100)
        sys.stdout = self.printstream
        self.printstream.write_signal.connect(self.print_to_gui)
        
        logdir = os.path.join(os.path.dirname(__file__), 'logs')
        if not os.path.exists(logdir):
            os.makedirs(logdir)
        logfile = datetime.datetime.now().strftime("%Y-%m-%d") + '.txt'     
        file_handler = logging.FileHandler(filename=os.path.join(logdir, logfile))
        
        file_format = logging.Formatter(fmt='%(levelname)s: %(asctime)s from '
                '%(name)s in %(funcName)s: %(message)s')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(file_format)
        self.logger.addHandler(file_handler)
        
        screen_handler = logging.StreamHandler(stream=self.printstream)
        screen_format = logging.Formatter(fmt='%(asctime)s - %(message)s')
        screen_handler.setLevel(logging.INFO)
        screen_handler.setFormatter(screen_format)
        self.logger.addHandler(screen_handler)
        
        self.logger.setLevel(logging.DEBUG)
        
        self.logger.debug('Start of program execution '
                '{0}'.format(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        
        #Set thread priority for the GUI thread to be non-laggy
        QtCore.QThread.currentThread().setPriority(QtCore.QThread.HighPriority)
        
        # Initialize the basic plot area
        canvas = SpectrogramCanvas(Figure())
        SpectrogramNavBar(canvas, self)

        self.set_canvas(canvas, self.plot_vl)
        
        #set up the dictionary of signals to their default slots
        self.signals = {
            self.entropy_checkbox.stateChanged:
                    lambda *args: self.plot('entropy'),
            self.power_checkbox.stateChanged:
                    lambda *args: self.plot('power'),
            self.classes_checkbox.stateChanged:
                    lambda *args: self.plot('classification'),
                    
            self.play_button.clicked:
                    lambda *args: self.click_play_button_callback(),
            
            #Set up menu callbacks
            self.action_load_files.triggered:
                    lambda *args: self.select_files_callback(),
            self.action_load_folder.triggered:
                    lambda *args: self.select_folder_callback(),
            self.action_load_nn.triggered:
                    lambda *args: self.load_neural_net_callback(),
            
            self.action_new_nn.triggered:
                    lambda *args: self.create_new_neural_net_callback(),
            
            self.action_save_all_motifs.triggered:
                    lambda *args: self.save_motifs_callback('all'),
            self.action_save_current_motif.triggered:
                    lambda *args: self.save_motifs_callback('current'),
            self.action_save_nn.triggered:
                    lambda *args: self.save_neural_net_callback(),
            
            self.action_classify_all.triggered:
                    lambda *args: self.auto_classify_callback('all'),
            self.action_classify_current.triggered:
                    lambda *args: self.auto_classify_callback('current'),
            
            self.action_find_all_motifs.triggered:
                    lambda *args: self.find_motifs_callback('all'),
            self.action_find_current_motifs.triggered:
                    lambda *args: self.find_motifs_callback('current'),
            
            self.action_serialize_active_song.triggered:
                    lambda *args: self.serialize_song_callback(),
            self.action_deserialize_song.triggered:
                    lambda *args: self.deserialize_song_callback(),
            
            self.song_table.cellDoubleClicked:
                    lambda r, c, *args: self.table_clicked_callback('songs', r),
            self.motif_table.cellDoubleClicked:
                    lambda r, c, *args: self.table_clicked_callback('motifs', r),
        }
        
        #Enumerate functions to be called when each async call is terminated
        self.async_cleanup_calls = {
            'load_files_async': [lambda: self.update_table_callback('songs')],
            'text_thread_test':[
                    lambda: self.print_to_gui('closing test 1'), 
                    lambda: self.print_to_gui('closing test 2')
                    ],
            'table_clicked_async':[lambda: self.show_active_song_callback()],
            'load_neural_net_async': [],
            'create_new_neural_net_async': [],
            'save_neural_net_async':[],
            'deserialize_song_async':[
                    lambda: self.update_table_callback('songs'), 
                    lambda: self.show_active_song_callback()
                    ],
            'serialize_song_async':[],
            'save_motifs_async':[],
            'auto_classify_async':[lambda: self.show_active_song_callback()],
            'find_motifs_async':[lambda: self.update_table_callback('motifs')]
            }
        
        self.connect_signals(init=True)
        self.threads = []
        
        #Initialize the collection of assorted parameters
        #Not currently customizable, maybe will make interface later
        defaultlayers = [
                {'type':'Convolution2D', 'args':(16,3,1,), 'kwargs':{'border_mode':'same'}},
                {'type':'Activation', 'args':('relu',)},
                {'type':'Convolution2D', 'args':(16,3,1,), 'kwargs':{'border_mode':'same'}},
                {'type':'Activation', 'args':('relu',)},
                {'type':'MaxPooling2D', 'kwargs':{'pool_size':(2,1,)}},
                {'type':'Dropout', 'args':(0.25,)},
                {'type':'Flatten'},
                {'type':'Dense', 'args':(256,)},
                {'type':'Activation', 'args':('relu',)},
                {'type':'Dropout', 'args':(0.5,)},
                {'type':'Dense', 'args':(32,)},
                {'type':'Activation', 'args':('relu',)},
                {'type':'Dropout', 'args':(0.5,)},
                ]
        
        #So many
        #spectrogram/display, net/training, classification/discovery
        self.params = {'load_downsampling':1, 'time_downsample_disp':1, 
                       'freq_downsample_disp':1,  'split':600, 'vmin':-80, 
                       'vmax':-40, 'nfft':512, 'fft_time_window_ms':10, 
                       'fft_time_step_ms':2, 'process_chunk_s':60, 
                       
                       'layers':defaultlayers, 
                       'loss':'categorical_crossentropy', 'optimizer':'adadelta',
                       'min_freq':440.0, 'epochs':30, 'batch_size':100, 
                       'validation_split':0.05, 'img_cols':1, 'img_rows':128, 
                       
                       'power_threshold':-90, 'medfilt_time':0.01, 
                       'smooth_time':0.01, 'join_gap':1.0, 'min_density':0.8, 
                       'min_dense_time':0.5
                       }
        
        self.analyzer = AudioAnalyzer(**self.params)
        
        self.player = pyaudio.PyAudio()
        
        self.canvas.draw_idle()
        self.show()
        
        self.logger.info('Finished with initialization')
        
    @QtCore.pyqtSlot(str)
    def print_to_gui(self, text):
        self.printerbox.write(text)
        
    @async_gui_call
    def text_thread_test(self, strval, intval):
        print 'Strval: {0} intval: {1}'.format(strval, intval)
        for _ in range(10):
            print '{0} - not error text?'.format(time.time())
            time.sleep(0.1)
        for _ in range(10):
            self.logger.info('{0} - info text?'.format(time.time()))
            time.sleep(0.3)
        for _ in range(10):
            self.logger.error('{0} - error text?'.format(time.time()))
            time.sleep(0.3)
    
    def async_call_cleanup(self, name):
        self.logger.debug('Ending async call to {0}'.format(name))
        
        for f in self.async_cleanup_calls[name]:
            f()
        
        self.threads = [t for t in self.threads if not t.isFinished()]
                
        if not self.threads:
            self.connect_signals()
        
    def connect_signals(self, init=False):
        '''Connect all GUI control signals to their relevant slots
        
        This method has been put in a function because it will be used in a 
        threaded application
        
        Keyword Arguments:
            init: boolean value indicating that this is the first time calling
                the function
        '''
        
        self.logger.debug('Connecting signals')
        for sig, slot in self.signals.items():
            if not init:
                sig.disconnect()
            
            #slot is a function or lambda
            #slot takes a known number of arguments (
            sig.connect(slot)
    
    def set_signals_busy(self):
        '''Disconnect all signals and reroute them to busy_alert
        
        This prevents much (but not all) of the GUI interaction the user has
        in a multithreaded program, but alerts the user to why their control
        has been removed
        '''
        self.logger.debug('Setting signals as busy')
        for sig in self.signals.keys():
            sig.disconnect()
            sig.connect(self.busy_alert)
    
    def busy_alert(self):
        '''Function to call for all GUI signals when something is processing'''
        
        self.logger.warning('Cannot execute that function during processing')
        self.logger.warning('Running processes are: ')
        for t in self.threads:
            self.logger.warning('Thread {0} is running {1}'.format(id(t), t.name))
           
    def set_canvas(self, canvas, loc):
        """Set the SpectrogramCanvas for this GUI
        
        Assigns the given canvas to be this GUI's canvas, connects any
        relevant slots, and places the canvas and its tools into the loc 
        container
        """
        loc.addWidget(canvas)
        
        for t in canvas.tools.values():
            loc.addWidget(t)
            
        self.canvas = canvas
    
    @QtCore.pyqtSlot()
    def select_files_callback(self):
        """Load one or more wav files as SongFiles"""
        self.logger.debug('Clicked the file select button')
              
        file_names = QtGui.QFileDialog.getOpenFileNames(self, 'Select file(s)', 
                '', 'WAV files (*.wav)')
        if file_names:
            self.load_files_async(file_names)
        else:
            self.logger.debug('Cancelled file select')
    
    @QtCore.pyqtSlot()
    def select_folder_callback(self):
        """Load all .wav files in a folder and all its subfolders as SongFiles"""
        
        self.logger.debug('Clicked the folder select button')
              
        folder_name = QtGui.QFileDialog.getExistingDirectory(self, 'Select folder')
        self.logger.info('selected %s', str(folder_name))
        if folder_name:
            files = self.find_files(str(folder_name), '*.wav') + self.find_files(str(folder_name), '*.WAV')
            self.load_files_async(files)
        else:
            self.logger.debug('Cancelled file select')

    @async_gui_call
    def load_files_async(self, file_names):
        """Load a list of wave files as SongFiles"""
        
        for f in file_names:
            self.logger.debug('Loading the file %s', str(f))
            
            new_songs = SongFile.load(
                            str(f),
                            downsampling=self.params['load_downsampling']
                            )
            
            self.logger.info('Loaded %s as %d SongFiles', str(f), 
                    len(new_songs))
            
            self.analyzer.songs.extend(new_songs)
    
    @QtCore.pyqtSlot(str)
    def update_table_callback(self, name):
        """Display information on loaded SongFiles in the table"""
        if name=='songs':
            data = self.analyzer.songs
            table = self.song_table
        elif name=='motifs':
            data = self.analyzer.motifs
            table = self.motif_table
        else:
            self.logger.warning('No table %s, cannot update', name)
            return
                
        for row,songfile in enumerate(data):
            if table.rowCount() == row:
                table.insertRow(row)
                
            for col, item in enumerate(self.create_table_row_items(songfile)):
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
                
                table.setItem(row, col, item)
            
    def create_table_row_items(self, sf):
        
        namecol = QtGui.QTableWidgetItem(sf.name)

        m, s = divmod(sf.start, 60)
        startcol = QtGui.QTableWidgetItem("{:02d}:{:06.3f}".format(int(m), s))
        
        m, s = divmod(sf.length, 60)
        lengthcol = QtGui.QTableWidgetItem("{:02d}:{:06.3f}".format(int(m), s))
        
        return [namecol, startcol, lengthcol]
    
    @QtCore.pyqtSlot(str, int)
    def table_clicked_callback(self, table, row):
        self.table_clicked_async(table, row)
    
    @async_gui_call
    def table_clicked_async(self, table, row):
        if table == 'motifs':
            self.analyzer.set_active(self.analyzer.motifs[row])
        elif table == 'songs':
            self.analyzer.set_active(self.analyzer.songs[row])
        else:
            self.logger.warning('Unknown table %s clicked, cannot display song', table)
        
        #self.show_active_song_callback()
    
    @QtCore.pyqtSlot()
    def load_neural_net_callback(self):
        """Load a folder containing the files necessary to specify a neural net"""
        self.logger.debug('Clicked the NN load button')
              
        folder = str(QtGui.QFileDialog.getExistingDirectory(parent=self, 
                caption='Select a folder containing the required NN files'))
        
        self.load_neural_net_async(folder)
        
    @async_gui_call
    def load_neural_net_async(self, folder):
        if folder:
            try:
                net = self.analyzer.load_neural_net(folder)
            except (IOError, KeyError):
                self.logger.error('No valid neural net in that file')
            else:
                self.analyzer.classifier = net
                shape = self.analyzer.classifier.layers[0].input_shape
                self.params['img_rows'] = shape[2]
                self.params['img_cols'] = shape[3]
                self.analyzer.params['img_rows'] = shape[2]
                self.analyzer.params['img_cols'] = shape[3]
        else:
            self.logger.debug('Cancelled loading of neural net')
    
    @QtCore.pyqtSlot()
    def create_new_neural_net_callback(self):
        """Uses the Analyzer's active_song to construct and train a neural net"""
        
        self.create_new_neural_net_async()
        
    @async_gui_call
    def create_new_neural_net_async(self):
        start = time.time()
        self.analyzer.classifier = self.analyzer.build_neural_net()
        
        #then, train it
        self.analyzer.train_neural_net()
        
        self.logger.info('{0} seconds elapsed building and training the '
                'classifier'.format(time.time()-start))
    
    @QtCore.pyqtSlot()
    def save_neural_net_callback(self):
        """Save the analyzer's current neural net to a file to avoid training"""
        self.logger.debug('Clicked the NN save button')
              
        fullpath = str(QtGui.QFileDialog.getSaveFileName(parent=self, 
                caption='Enter folder name to save the required NN files'))
        
        self.save_neural_net_async(fullpath)
        
    @async_gui_call  
    def save_neural_net_async(self, fullpath):
        if fullpath:
            self.logger.info('Saving NN to %s', fullpath)
            if not os.path.exists(fullpath):
                os.makedirs(fullpath)
            self.analyzer.export_neural_net(fullpath)
        else:
            self.logger.debug('Cancelled save neural net')
            
        self.logger.info('Neural net saved!')
            
    @QtCore.pyqtSlot()
    def deserialize_song_callback(self):
        """Load a pickled song with its classification and make it active"""
        self.logger.debug('Clicked the deserialize song button')
        
        file_name = QtGui.QFileDialog.getOpenFileName(self, 'Select serialized song', 
                '', 'PKL files (*.pkl)')
        
        self.deserialize_song_async(file_name)
    
    @async_gui_call
    def deserialize_song_async(self, file_name):
        if file_name:
            sf = SongFile.deserialize(file_name)
            self.analyzer.songs.append(sf)
            self.analyzer.set_active(sf)
        else:
            self.logger.debug('Cancelled file select')
    
    @QtCore.pyqtSlot()
    def serialize_song_callback(self):
        """Save the active song as a serialize file, preserving classification"""
        self.logger.debug('Clicked the serialize active song button')
        
        destination = str(QtGui.QFileDialog.getExistingDirectory(self, 
                    'Choose location for serialized song'))
        
        self.serialize_song_async(destination)
    
    @async_gui_call
    def serialize_song_async(self, destination):
        self.analyzer.active_song.serialize(destination=destination)

    @QtCore.pyqtSlot(str)
    def save_motifs_callback(self, mode):
        if mode == 'all':
            destination = str(QtGui.QFileDialog.getExistingDirectory(self, 
                    'Select folder'))
            self.save_motifs_async(mode, destination)

        elif mode == 'current':
            destination = str(QtGui.QFileDialog.getSaveFileName(self, 
                    'Choose filename and save location'))
            self.save_motifs_async(mode, destination)

    @async_gui_call
    def save_motifs_async(self, mode, destination):
        if mode == 'all':
            for mf in self.analyzer.motifs:
                mf.export(destination = destination)
                
        if mode == 'current':
            self.analyzer.active_song.export(
                    destination=os.path.dirname(destination), 
                    filename=os.path.basename(destination)
                    )
    
    @QtCore.pyqtSlot()
    def click_play_button_callback(self):
        """Callback for clicking the GUI button"""
        try:
            if self.play_button.isChecked():
                self.start_playback()
                self.logger.debug('Playback started')
            else:
                self.logger.debug('Ending playback')  
                self.stop_playback()    
        except AttributeError:
            self.logger.error('Could not execute playback, no song prepared')
            self.play_button.setChecked(not self.play_button.isChecked())
                     
    def start_playback(self):
        """Open and start a PyAudio stream
        
        Raises AttributeError if self.analyzer.active_song is not set
        """
        self.stream = self.player.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=int(self.analyzer.active_song.Fs),
                output=True,
                stream_callback=self.play_audio,
                frames_per_buffer=4096)
        
        self.stream.start_stream()
 
    def stop_playback(self):
        """Stop and close a PyAudio stream
        
        Raises AttributeError if self.stream is not set
        """
        if self.stream.is_active():
            self.stream.stop_stream()
            self.stream.close()

    def play_audio(self, in_data, frame_count, time_info, status):
        """Callback for separate thread that plays audio
        
        This is responsible for moving the marker on the canvas, and since the
        stream auto-dies when it reaches the end of the data, no handling is
        needed to make sure the marker stops moving
        """
        
        index = int(self.canvas.marker * self.analyzer.active_song.Fs)
        data = self.analyzer.active_song.data[index:index+frame_count]
        
        self.canvas.set_marker((index+frame_count)/self.analyzer.active_song.Fs)
        
        return (data, pyaudio.paContinue)    
    
    @QtCore.pyqtSlot()
    def show_active_song_callback(self):
        """Put all applicable data from the Model to the View
        
        This function assumes all preprocessing has been completed and merely
        looks at the state of the model and displays it
        """
        self.logger.info('Beginning plot of spectrogram... please wait')  
        for p in ['spectrogram', 'classification', 'entropy', 'power']:
            self.plot(p)
        
        self.canvas.set_marker(0)
        self.canvas.set_selection(())
        
    def keyPressEvent(self, e):
        """Listens for a keypress
        
        If the keypress is a number and a region has been selected with the
        select tool, the keypress will assign the value of that number to be
        the classification of the selected region
        """
        if (e.text() in [str(i) for i in range(10)] and 
                self.canvas.current_selection):
            indices = np.searchsorted(self.analyzer.active_song.time, 
                    np.asarray(self.canvas.current_selection))
            
            self.analyzer.active_song.classification[indices[0]:indices[1]] = int(e.text())
        
            self.plot('classification')
            self.canvas.set_selection(())  
    
    @QtCore.pyqtSlot(str)
    def plot(self, plot_type):
        """Show active song data on the plot
        
        This method relies on the state of the GUI checkboxes to know whether or
        not a type of data should be shown or hidden.
        
        Inputs:
            plot_type: string specifying which set of data to display
        """
        try:
            t_step = self.params['time_downsample_disp']
        except KeyError:
            self.logger.warning('Missing time domain display downsampling ratio')
            t_step = 1
            
        try:
            f_step = self.params['freq_downsample_disp']
        except KeyError:
            self.logger.warning('Missing frequency domain display downsampling ratio')
            f_step = 1
            
        try:  
            title = 'Active Song: '+str(self.analyzer.active_song)
            time = self.analyzer.active_song.time[::t_step]
            freq = self.analyzer.active_song.freq[::f_step]
            classification = self.analyzer.active_song.classification[::t_step]
            entropy = self.analyzer.active_song.entropy[::t_step]
            power = self.analyzer.active_song.power[::t_step]
            disp_Sxx = 10*np.log10(np.flipud(self.analyzer.Sxx[::t_step, ::f_step]))
        except AttributeError:
            self.logger.warning('No active song, cannot display plot %s', plot_type)
            return
        
        if plot_type == 'spectrogram':
            self.canvas.display_spectrogram(time, freq, disp_Sxx, title=title, **self.params)
        elif plot_type == 'classification':
            show = self.classes_checkbox.isChecked()
            self.canvas.display_classification(time, classification, show=show)
        elif plot_type == 'entropy':
            show = self.entropy_checkbox.isChecked()
            self.canvas.display_entropy(time, entropy, show=show)
        elif plot_type == 'power':
            show = self.power_checkbox.isChecked()
            self.canvas.display_power(time, power, show=show)
        else:
            self.logger.warning('Unknown plot type %s, cannot plot', plot_type)

    @QtCore.pyqtSlot(str)
    def auto_classify_callback(self, mode):
        self.auto_classify_async(mode)
        
    @async_gui_call
    def auto_classify_async(self, mode):
        
        start = time.time()
        count = 0
        try:
            if mode == 'all':
                for sf in self.analyzer.songs:
                    self.analyzer.set_active(sf)
                    self.analyzer.classify_active()
                    count += 1
                
            elif mode == 'current':
                    self.analyzer.classify_active()
                    count += 1
        except AttributeError:
            self.logger.error('No neural net yet trained, cannot classify songs')
        else:
            self.logger.info('Took {0:2.3f} seconds to classify {1} songs'.format(time.time()-start, count))
    
    @QtCore.pyqtSlot(str)
    def find_motifs_callback(self, mode):
        self.find_motifs_async(mode)
    
    @async_gui_call
    def find_motifs_async(self, mode):
        start = time.time()
        count = 0
        if mode == 'all':
            for sf in self.analyzer.songs:
                self.analyzer.motifs += sf.find_motifs(**self.params)
                count += 1
            #self.update_table_callback('motifs')
            
        elif mode == 'current':
            active_s = self.analyzer.active_song
            self.analyzer.motifs += active_s.find_motifs(**self.params)
            #self.update_table_callback('motifs')
            count += 1
            
        self.logger.info('Took {0:2.3f} seconds to find motifs in {1} SongFile(s)'.format(time.time()-start, count))
       
    def find_files(self, directory, pattern):
        """Return filenames matching pattern in directory"""
        
        return [os.path.join(directory, fname) 
                for fname in os.listdir(directory) 
                if fnmatch.fnmatch(os.path.basename(fname), pattern)]
    
        
class SpectrogramCanvas(FigureCanvas, QtCore.QObject):
    """Subclasses the FigureCanvas to provide features for spectrogram display
    
    Of primary interest is that this class keeps record of all the axes on the
    plot by name, with independent y scales but a uniform x-scale.  The primary
    intent of this class is to bound the x-scale so that it is impossible to
    scroll, pan, or zoom outside of the domain set in the public instance
    variable x_constraint.  Anything that moves that plot that is not contained
    within this class should emit a signal which should be bound to this class's
    'navigate' method.  navigate corrects for any navigation not done by the 
    SpectrogramCanvas and then redraws.
    """
    logger = logging.getLogger('JLAA.SpectogramCanvas')
    
    def __init__(self, figure_):
        
        #So, multiple inheritance is fun
        #This works if it goes QObject, FigureCanvas
        #Breaks if it goes FigureCanvas, QObject - and in weird ways too
        #Using super seeeeeems not broken?  We hope
        #QtCore.QObject.__init__(self)
        #FigureCanvas.__init__(self, figure_)
        super(SpectrogramCanvas, self).__init__(figure_)

        #Extent of the spectrogram data, for homing and as domain bound
        self.extent = ()
        #Dictionary mapping str->axis object
        self.axis_dict = {}
        #Ordered list of axis names, in order added
        self.axis_names = []
        
        self.tools = {}
        
        self.image = None
        
        self.last_gui_refresh_time = time.time()
        self.marker = 0
        self.current_selection = ()
        
    def add_tool(self, tool):
        """Add the tool to the tools dictionary and connect any known signals"""
        
        self.tools[type(tool).__name__] = tool
        
        if isinstance(tool, SpectrogramNavBar):
            tool.navigate.connect(self.navigate)
            tool.set_selection.connect(self.set_selection)
            tool.set_marker.connect(self.set_marker)
    
    @QtCore.pyqtSlot(dict)
    def navigate(self, kwargs):
        """Receive all navigation signals that this canvas must deal with"""
        
        try:
            navtype = kwargs['type']
        except KeyError:
            self.error('Invalid navigation signal or command %s, no type'
                    ' provided', str(kwargs))
            return
        
        if navtype == 'drag_pan':
            try:
                ax = kwargs['axis']
                button = kwargs['button']
                key = kwargs['key']
                x = kwargs['x']
                y = kwargs['y']
                pre_drag_x = kwargs['pre_drag_x']
                pre_drag_y = kwargs['pre_drag_y']
            except KeyError:
                self.logger.error('Invalid drag command or signal, cannot execute')
                return
            
            ax.drag_pan(button, key, x, y)
            
            if not self.valid(ax.get_xlim()):
                self.set_domain(pre_drag_x)
                
            if ax is not self.axis_dict['spectrogram']:
                ax.set_ylim(pre_drag_y) 
                
        elif navtype == 'release_zoom':
            try:
                ax = kwargs['axis']
                key = kwargs['key']
                tup = kwargs['zoom_tuple']
                mode = kwargs['mode']
            except KeyError:
                self.logger.error('Invalid drag command or signal, cannot execute')
                return
            
            if key == 1:
                direction = 'in'
            elif key == 3:
                direction = 'out'
                
            ax._set_view_from_bbox(tup, direction, mode, False, False)   
            
            if direction=='out' and not self.valid(ax.get_xlim()):
                self.set_domain(self.extent[0:2])
                   
        elif navtype == 'forward':
            #Get any plot, read the plot domain, move left by 25% of domain
            try:
                ax = self.axis_dict[self.axis_names[0]]
            except IndexError:
                self.logger.warning("Scrolling irrelevant, no plots at this time")
            else:
                xbounds = ax.get_xlim()
                width = xbounds[1] - xbounds[0]
                if xbounds[1]+0.25*width < self.extent[1]:
                    dx = 0.25*width
                else:
                    dx = self.extent[1] - xbounds[1]
                    
                new_bounds = (xbounds[0]+dx, xbounds[1]+dx)
                
                self.set_domain(self.validate(new_bounds))  
                  
        elif navtype == 'back':
            #Get any plot, read the plot domain, move left by 25% of domain
            try:
                ax = self.axis_dict[self.axis_names[0]]
            except IndexError:
                self.logger.warning("Scrolling irrelevant, no plots at this time")
            else:
                xbounds = ax.get_xlim()
                width = xbounds[1] - xbounds[0]
                if xbounds[0]-0.25*width > self.extent[0]:
                    dx = 0.25*width
                else:
                    dx = xbounds[0] - self.extent[0]
                    
                new_bounds = (xbounds[0]-dx, xbounds[1]-dx)
                
                self.set_domain(self.validate(new_bounds))  
                      
        elif navtype == 'home':
            self.set_domain(self.extent[0:2])
            self.set_range('spectrogram', self.extent[2:4])

        else:
            self.logger.warning('Unknown navigate type %s', navtype)
        
        self.draw_idle()
        
    @QtCore.pyqtSlot(tuple)
    def set_selection(self, sel):
        if not sel:
            self.current_selection = ()
            self.drawRectangle(None)
        else:
            self.current_selection = sel
            
        self.logger.debug('Selection set to %s', str(self.current_selection))
    
    @QtCore.pyqtSlot(float)
    def set_marker(self, marker):
        """Sets the marker, but does not update the GUI unless the change in
        values from the last GUI value is significant
        """
        
        self.logger.debug('Setting marker to %0.4f', marker)
        self.marker = marker
        t = time.time()
        
        if t - self.last_gui_refresh_time > 0.05:
            try:
                ax = self.axis_dict['marker']
            except KeyError:
                self.add_axis('marker')
                ax = self.axis_dict['marker']
            
            if ax.lines:
                ax.lines.remove(ax.lines[0])
            
            ax.plot([self.marker, self.marker],[0,1], 'k--', linewidth=2, 
                    scalex=False, scaley=False)
            self.set_range('marker', (0,1))
            self.draw_idle()
            self.last_gui_refresh_time = t
                
    def add_axis(self, name):
        """Add one axis to this plot, and associate it with name"""
        
        if not self.axis_dict:
            self.axis_dict[name] = self.figure.add_subplot(111)
            self.axis_names.append(name)
        else:
            self.axis_dict[name] = self.axis_dict[self.axis_names[0]].twinx()
            self.axis_names.append(name)
                
        if name in ['marker', 'classification', 'power', 'entropy']:
            self.axis_dict[name].yaxis.set_visible(False) 
            
    def set_domain(self, x_domain):
        """Set the domain for ALL plots (which must share an x-axis domain)"""
        
        try:
            assert self.valid(x_domain)
        except AssertionError:
            self.logger.warning("Assert failed: the domain command %s is" 
                    "out of bounds", str(x_domain))
            return
     
        self.logger.debug('Setting the plot domain to %s', str(x_domain))

        for name in self.axis_names:
            ax = self.axis_dict[name]
            self.logger.debug('Setting domain for axis %s to %s', name, str(x_domain))
            ax.set_xlim(x_domain)
            
        self.draw_idle()
        
    def set_range(self, name, y_range):
        """Set the y-axis range of the plot associated with name"""
        
        try:
            ax = self.axis_dict[name]
        except KeyError:
            self.logger.warning('No such axis %s to set the range', name)
            return
        
        self.logger.debug('Setting the range of %s to %s', name, str(y_range))
        ax.set_ylim(y_range)
        
        self.draw_idle()
        
    def set_all_ranges(self, yranges):
        """Set the range (y-axis) of all plots linked to this NavBar"""
        
        try:
            for idx, yrange in enumerate(yranges):
                self.set_range(self.axis_names[idx], yrange)
        except IndexError:
            self.logger.warning('Too many yranges provided, there are only %d' 
                    'axes available', len(self.axis_names)+1)
            return
        
    def valid(self, xlims):
        if not xlims:
            return False
        if not self.extent:
            return True
        else:
            return xlims[0] >= self.extent[0] and xlims[1] <= self.extent[1]
        
    def validate(self, xlims):
        if self.valid(xlims):
            return xlims
        else:
            return (max(xlims[0], self.extent[0]), min(xlims[1], self.extent[1]))
         
            
    def display_spectrogram(self, t, f, Sxx, **params):
        """Fetches spectrogram data from analyzer and plots it
        
        NO display method affects the domain in any way.  That must be done
        external to the display method
        """   
          
        try:
            ax = self.axis_dict['spectrogram']
        except KeyError:
            self.add_axis('spectrogram') 
            ax = self.axis_dict['spectrogram']
            
        try:
            vmin = params['vmin']
        except KeyError:
            self.logger.warning('No parameter "vmin", using data minimum')
            vmin = np.min(Sxx)
            
        try:
            vmax = params['vmax']
        except KeyError:
            self.logger.warning('No parameter "vmax", using data maximum')
            vmax = np.max(Sxx)
            
        title = params.get('title', '')
        
        halfbin_time = (t[1] - t[0]) / 2.0
        halfbin_freq = (f[1] - f[0]) / 2.0
        
        # this method is much much faster!
        # center bin
        self.extent = (t[0] - halfbin_time, t[-1] + halfbin_time,
                  f[0] - halfbin_freq, f[-1] + halfbin_freq)
        
        self.image = ax.imshow(Sxx, 
                interpolation="nearest", 
                extent=self.extent,
                cmap='gray_r',
                vmin=vmin,
                vmax=vmax
                )
        
        ax.set_title(title, loc='left')
        ax.axis('tight')

        self.set_domain(self.extent[0:2])
        self.set_range('spectrogram', self.extent[2:4])
  
        self.draw_idle() 
        
    def display_classification(self, t, classes, show=True):
        """Fetches classification data from analyzer and plots it
        
        NO display method affects the domain in any way.  That must be done
        external to the display method
        """
        
        try:
            ax = self.axis_dict['classification']
        except KeyError:
            self.add_axis('classification')
            ax = self.axis_dict['classification']
        
        if ax.lines:
            ax.lines.remove(ax.lines[0])
            
        l, = ax.plot(t, classes, 'b-', scalex=False, scaley=False)
        
        self.set_range('classification', (0, np.amax(classes)+1))
        #self.set_range('classification', (0, 1))
        l.set_visible(show)

        self.draw_idle() 
        
        
    def display_entropy(self, t, entropy, show=True):

        try:
            ax = self.axis_dict['entropy']
        except KeyError:
            self.add_axis('entropy')
            ax = self.axis_dict['entropy']
             
        
        if ax.lines:
            ax.lines.remove(ax.lines[0])
            
        l, = ax.plot(t, entropy, 'g-', scalex=False, scaley=False)
           
        self.set_range('entropy', (min(entropy), max(entropy)))
        #self.set_range('entropy', (0, 1))

        l.set_visible(show)

        self.draw_idle()  
        
    def display_power(self, t, power, show=True):
        try:
            ax = self.axis_dict['power']
        except KeyError:
            self.add_axis('power')
            ax = self.axis_dict['power']
        
        if ax.lines:
            ax.lines.remove(ax.lines[0])
            
        l, = ax.plot(t, power, 'r-', scalex=False, scaley=False)

        self.set_range('power', (min(power), max(power)))
        #self.set_range('power', (0, 1))

        l.set_visible(show)
        
        self.draw_idle()        
         
class SpectrogramNavBar(NavigationToolbar2QT):
    """Provides a navigation bar specially configured for spectrogram interaction
    
    This class overrides a number of the methods of the standard 
    NavigationToolbar2QT and NavigationToolbar2, and adds some convenience
    methods.

    The navigation bar tools have been updated.  The left and right buttons 
    scroll left and right, rather than moving between views.  The pan and zoom 
    buttons are identical, but with the horizontal bound enforced.  Several 
    buttons are removed, and a 'select' button has been added which is used for 
    manual classification of data.
    
    Signals:
        'navigate': called any time an action is take which would change the 
            canvas x_lims or y_lims (bounds).
        'set_marker': called in select mode to move the song marker
        'set_selection': called in select mode to set a selection and also to 
            cancel a selection when necessary
    """
    
    #List of signals for emitted by this class
    navigate = QtCore.pyqtSignal(dict)
    set_marker = QtCore.pyqtSignal(float)
    set_selection = QtCore.pyqtSignal(tuple)
    logger = logging.getLogger('JLAA.SpectrogramNavBar')
    
    def __init__(self, canvas_, parent_, *args, **kwargs):  
        """Creates a SpectrogramNavigationBar instance
        
        Requires that canvas_ be a SpectrogramCanvas
        """ 
        
        #initialize logging
            
        self.toolitems = (
            ('Home', 'Reset original view', 'home', 'home'),
            ('Back', 'Scroll left', 'back', 'back'),
            ('Forward', 'Scroll right', 'forward', 'forward'),
            (None, None, None, None),
            ('Pan', 'Pan axes with left mouse, zoom with right', 'move', 'pan'),
            ('Zoom', 'Zoom to rectangle', 'zoom_to_rect', 'zoom'),
            (None, None, None, None),
            ('Save', 'Save the figure', 'filesave', 'save_figure'),
        )
        
        NavigationToolbar2QT.__init__(self, canvas_, parent_, coordinates=False)
                
        self.custom_toolitems = (
            (None, None, None, None),
            ('Select', 'Cursor with click, select with drag', 'select1', 'select'),
        )
   
        self.icons_dir = os.path.join(os.path.dirname(__file__), 'icons')
            
        self.logger.debug('Icons directory %s', self.icons_dir)

        for a in self.findChildren(QtGui.QAction):
            if a.text() == 'Customize':
                self.removeAction(a)
                break
             
        for text, tooltip_text, image_file, callback in self.custom_toolitems:
            if text is None:
                self.addSeparator()
            else:
                a = self.addAction(self.local_icon(image_file + '.png'),
                        text, getattr(self, callback))
                self._actions[callback] = a
                if callback in ['select', 'scale']:
                    a.setCheckable(True)
                if tooltip_text is not None:
                    a.setToolTip(tooltip_text)
         
        self.addSeparator() 
         
        self.locLabel = QtGui.QLabel("", self)
        labelAction = self.addWidget(self.locLabel)
        labelAction.setVisible(True) 
        self.coordinates = True
                    
        self._idSelect = None
        
        try:
            canvas_.add_tool(self)
        except AttributeError as e:
            self.logger.error('Cannot initialize SpectrogramNavBar - canvas '
                    'type not valid')
            raise e
        
    def local_icon(self, name):
        """Load a file in the /icons folder as a QIcon"""
        
        imagefile = os.path.join(self.icons_dir, name)
        
        self.logger.debug('Icon image file %s', imagefile)
        return QtGui.QIcon(imagefile)


    def forward(self, *args):
        """Button callback for clicking the forward button
        
        OVERRIDE the foward function in backend_bases.NavigationToolbar2
        Emits a signal causing the SpectrogramCanvas to scroll right
        """
        
        self.logger.debug('Clicked the forward button')
        
        self.set_selection.emit(())
        self.navigate.emit({'type':'forward'})
     
    def back(self, *args):
        """Button callback for clicking the back button
        
        OVERRIDE the back function in backend_bases.NavigationToolbar2
        Emits a signal causing the SpectrogramCanvas to scroll left
        """
        self.logger.debug('Clicked the back button')
        
        self.set_selection.emit(())
        self.navigate.emit({'type':'back'})
     
    def home(self, *args):
        """Button callback for clicking the home button
        
        Override the home method of backend_bases.NavigationToolbar2"""
        self.navigate.emit({'type':'home'})
            
    def drag_pan(self, event):
        """OVERRIDE the drag_pan function in backend_bases.NavigationToolbar2
        
        Adjusted to make sure limits are maintained
        """
        
        for a, _ in self._xypress:
            #safer to use the recorded button at the press than current button:
            #multiple buttons can get pressed during motion...

            drag_data = {
                    'type':'drag_pan',
                    'axis':a, 
                    'button':self._button_pressed, 
                    'key':event.key,
                    'x':event.x,
                    'y':event.y,
                    'pre_drag_x':a.get_xlim(),
                    'pre_drag_y':a.get_ylim()}

            self.navigate.emit(drag_data)
            
    def pan(self, *args):
        """Button callback for clicking the pan button"""
        self.set_selection.emit(())
        super(SpectrogramNavBar, self).pan(*args)
        
    def zoom(self, *args):
        """Button callback for clicking the zoom button"""

        self.set_selection.emit(())
        super(SpectrogramNavBar, self).zoom(*args)
        
    def release_zoom(self, event):
        """OVERRIDE the release_zoom method in backend_bases.NavigationToolbar2
        
        Emits a signal containing the data necessary to zoom the plot
        """
        
        self.logger.debug('Called release_zoom')
        
        for zoom_id in self._ids_zoom:
            self.canvas.mpl_disconnect(zoom_id)
        self._ids_zoom = []

        self.remove_rubberband()
        
        if not self._xypress:
            return

        x, y = event.x, event.y
        lastx, lasty, ax, _, _ = self._xypress[0]
        
        if abs(x - lastx) < 5 and abs(y - lasty) < 5:
            self._xypress = None
            self.release(event)
            return

        data = {
                'type':'release_zoom',
                'axis':ax,
                'key':self._button_pressed,
                'zoom_tuple':(lastx, lasty, x, y),
                'mode':self._zoom_mode
                }
        
        self.navigate.emit(data)
        
        self._xypress = None
        self._button_pressed = None

        self._zoom_mode = None

        self.push_current()
        self.release(event) 
            
    def _update_buttons_checked(self):
        """sync button checkstates to match active mode"""
        super(SpectrogramNavBar, self)._update_buttons_checked()
        self._actions['select'].setChecked(self._active == 'SELECT')
    
    def select(self, *args):
        """Activate the select tool. select with left button, set cursor with right"""

        self.logger.debug('Clicked the select button on the toolbar')

        if self._active == 'SELECT':
            self._active = None
        else:
            self._active = 'SELECT'
        if self._idPress is not None:
            self._idPress = self.canvas.mpl_disconnect(self._idPress)
            self.mode = ''

        if self._idRelease is not None:
            self._idRelease = self.canvas.mpl_disconnect(self._idRelease)
            self.mode = ''

        if self._active:
            self._idPress = self.canvas.mpl_connect(
                'button_press_event', self.press_select)
            self._idRelease = self.canvas.mpl_connect(
                'button_release_event', self.release_select)
            self.mode = 'select/set'
            self.canvas.widgetlock(self)
        else:
            self.canvas.widgetlock.release(self)

        self.set_message(self.mode)
        
        self._update_buttons_checked()

    def press_select(self, event):
        """the press mouse button in select mode callback"""

        # If we're already in the middle of a zoom, pressing another
        # button works to "cancel"
        self.remove_rubberband()
        
        if self._idSelect:
            self.canvas.mpl_disconnect(self._idSelect)
            self.release(event)
            self.draw()
            self._xypress = None
            self._button_pressed = None
            return

        if event.button == 1:
            self._button_pressed = 1
            self.logger.debug('Pressed left mouse to select region in '
                    'select mode')

        elif event.button == 3:
            self.logger.debug('Pressed right mouse button to place start mark'
                    ' in select mode')
            self._button_pressed = 3
        else:
            self._button_pressed = None
            return

        x, y = event.x, event.y
        #self._select_start = event.xdata

        # push the current view to define home if stack is empty
        if self._views.empty():
            self.push_current()

        self._xypress = []
        for i, a in enumerate(self.canvas.figure.get_axes()):
            if (x is not None and y is not None and a.in_axes(event)):
                self._xypress.append((x, y, a, i, a._get_view()))

        self._idSelect = self.canvas.mpl_connect('motion_notify_event', 
                self.drag_select)

        self.press(event)
    
    def drag_select(self, event):
        """drag mouse callback when select function is active"""
        
        if self._button_pressed == 3:
            self.set_marker.emit(event.xdata)
             
        elif self._button_pressed == 1:
            if self._xypress:
                x, y = event.x, event.y
                lastx, lasty, a, _, _ = self._xypress[0]
    
                # adjust x, last, y, last
                x1, y1, x2, y2 = a.bbox.extents
                x, lastx = max(min(x, lastx), x1), min(max(x, lastx), x2)
                y, lasty = max(min(y, lasty), y1), min(max(y, lasty), y2)
    
                self.draw_rubberband(event, x, y, lastx, lasty)
                    
    def release_select(self, event):
        """Release mouse callback when select button is checked"""
        
        self.logger.debug('Released mouse in select mode')
        
        self.canvas.mpl_disconnect(self._idSelect)
        self._idSelect = None

        if not self._xypress:
            return

        lastx, lasty, ax, _, _ = self._xypress[0]
    
        if self._button_pressed == 3 and event.xdata is not None:
            self.set_marker.emit(event.xdata)
    
        elif self._button_pressed == 1:
            # ignore singular clicks - 5 pixels is a threshold
            # allows the user to "cancel" a selection action
            # by selecting by less than 5 pixels
            if (abs(event.x - lastx) < 5 and abs(event.y - lasty) < 5):
                
                self.set_selection.emit(())
                
            else:
                x = event.x
                x1, _, x2, _ = ax.bbox.extents
                x, lastx = max(min(x, lastx), x1), min(max(x, lastx), x2)
                #y, lasty = max(min(event.y, lasty), y1), min(max(event.y, lasty), y2)

                self.logger.debug('Selected pixel domain %0.4f, %0.4f', x, lastx)
                
                inv = ax.transData.inverted()
                
                sel = inv.transform((x, 0))[0], inv.transform((lastx, 0))[0]
                
                self.logger.debug('Selected domain %s', str(sel))

                self.set_marker.emit(sel[0])
                self.set_selection.emit(sel)

        self._xypress = None
        self._button_pressed = None

        self.release(event)

        
    def _set_cursor(self, event):
        """OVERRIDE the _set_cursor method in backend_bases.NavigationToolbar2"""
         
        #self.logger.info('Calling set_cursor with active %s', self._active) 
         
        if not event.inaxes or not self._active:
            if self._lastCursor != cursors.POINTER:
                self.set_cursor(cursors.POINTER)
                self._lastCursor = cursors.POINTER
        else:
            if self._active == 'ZOOM':
                if self._lastCursor != cursors.SELECT_REGION:
                    self.set_cursor(cursors.SELECT_REGION)
                    self._lastCursor = cursors.SELECT_REGION
            elif (self._active == 'PAN' and
                  self._lastCursor != cursors.MOVE):
                self.set_cursor(cursors.MOVE)
                self._lastCursor = cursors.MOVE   
            elif (self._active == 'SELECT' and
                    self._lastCursor != cursors.SELECT_REGION):
                self.set_cursor(cursors.SELECT_REGION)
                self._lastCursor = cursors.SELECT_REGION

    
class OutLog:
    '''OutLog pipes output from a stream to a QTextEdit widget
    
    '''
    
    
    def __init__(self, edit, interval_ms=200):
        """

        """
        self.mutex = QtCore.QMutex()
        self.flag = False
        
        self.edit = edit
        self.cache = collections.deque()
        
        self.thread = QtCore.QThread()
        self.timer = QtCore.QTimer()
        self.timer.moveToThread(self.thread)
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(self.flush)
        self.thread.started.connect(self.timer.start)
        self.thread.start()
        
    def __del__(self):
        self.thread.quit()
        self.thread.wait()

    def write(self, m):
        locker = QtCore.QMutexLocker(self.mutex)

        for char in str(m):
            if char == '\r':
                if not self.flag:
                    self.edit.moveCursor(
                            QtGui.QTextCursor.StartOfLine,
                            mode=QtGui.QTextCursor.KeepAnchor
                            )
                    self.flag = True
                
                while char != '\n' and self.cache:
                    char = self.cache.pop()
                
                if char == '\n':
                    self.cache.append('\n')
                
            else:
                self.cache.append(char)
            
    @QtCore.pyqtSlot()
    def flush(self):  
        locker = QtCore.QMutexLocker(self.mutex)
        
        if self.flag:     
            self.edit.textCursor().removeSelectedText()
            self.flag = False
        
        if self.cache:
            self.edit.moveCursor(QtGui.QTextCursor.End)      
            self.edit.insertPlainText(''.join(self.cache))
            self.cache = []
            self.edit.moveCursor(QtGui.QTextCursor.End)
            
    

          
def main():  
    app = QtGui.QApplication(sys.argv)
      
    main = AudioGUI()
    sys.exit(app.exec_())
    
if __name__ == '__main__':
    main()
