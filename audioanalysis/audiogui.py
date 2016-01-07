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

from freqanalysis import AudioAnalyzer, SongFile
from PyQt4.uic import loadUiType

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt4agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT)
from matplotlib.backends.qt_compat import QtWidgets
from matplotlib.backend_bases import cursors

from PyQt4 import QtGui, QtCore

import logging, sys, os
import numpy as np

Ui_MainWindow, QMainWindow = loadUiType('main.ui')

class AudioGUI(Ui_MainWindow, QMainWindow):
    """AudioGUI docstring goes here TODO
    
    
    """
    

    def __init__(self,):
        """Initialization docstring goes here TODO
        
        
        """
        #Initialization of GUI from Qt Designer
        super(AudioGUI, self).__init__()
        self.setupUi(self)
        
        #Initialize logging
        self.logger = logging.getLogger('AudioGUI.logger')
        
        #Initialize text output to GUI
        sys.stdout = OutLog(self.console, sys.stdout)
        sys.stderr = OutLog(self.console, sys.stderr, QtGui.QColor(255,0,0) )
        
        logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
        
        # Initialize the basic plot area
        self.fig = Figure()
        self.canvas = FigureCanvas(self.fig)
        self.plot_vl.addWidget(self.canvas)
        
        self.toolbar = SpectrogramNavBar(self.canvas, self.plot_container)
        self.plot_vl.addWidget(self.toolbar)
        
        #Set up button callbacks
        self.open_file.clicked.connect(self.file_open_dialog)
        self.play_button.clicked.connect(self.click_play_button)
        
        #Initialize the collection of assorted parameters
        #Not currently customizable, maybe will make interface later
        self.params = {'load_downsampling':1, 'time_downsample_disp':1, 
                       'freq_downsample_disp':1, 'display_threshold':-400, 
                       'split':600, 'vmin':-90, 'vmax':-20, 'nfft':512, 
                       'fft_time_window_ms':10, 'fft_time_step_ms':2, 
                       'process_chunk_s':15,
                       }
            
        self.analyzer = AudioAnalyzer(**self.params)
        
        self.canvas.draw_idle()
        self.show()
        
        self.logger.info('Finished with initialization')
    
    def file_open_dialog(self):
        """Provide a standard file open dialog to import .wav data into the 
        model classes"""  
        self.logger.debug('Clicked the file select button')
              
        file_name = QtGui.QFileDialog.getOpenFileName(self, 'Open file', 
                '/home', 'WAV files (*.wav)')
        
        
        if file_name:
            self.logger.debug('Selected the file %s', str(file_name))

            self.file_name.setText(file_name)
            
            newest_sf = len(self.analyzer.songs)
            new_songs = SongFile.load(
                            str(file_name),
                            downsampling=self.params['load_downsampling']
                            )
            
            self.logger.info('Loaded %s as %d SongFiles', str(file_name), 
                    len(new_songs))
            
            self.analyzer.songs.extend(new_songs)
            
            self.analyzer.set_active(newest_sf)
            
            self.show_data()

        else:
            self.logger.debug('Cancelled file select')
    
    def click_play_button(self):
        if self.play_button.isChecked():
            self.logger.debug('Playback started')
            self.analyzer.start_playback(self.toolbar.playback)
        else:
            self.logger.debug('Ending playback')  
            self.analyzer.stop_playback()
        
    
    def show_data(self):
        """Put all applicable data from the Model to the View
        
        This function assumes all preprocessing has been completed and merely
        looks at the state of the model and displays it
        """
        self.display_spectrogram()

        self.display_classification()
        
        
        self.toolbar.x_constraint = self.analyzer.active_song.domain       
        self.toolbar.set_domain(self.analyzer.active_song.domain)

    def display_spectrogram(self):
        """Fetches spectrogram data from analyzer and plots it
        
        NO display method affects the domain in any way.  That must be done
        external to the display method
        """
        try:
            ax = self.toolbar.axis_dict['spectrogram']
        except KeyError:
            self.toolbar.add_axis('spectrogram') 
            ax = self.toolbar.axis_dict['spectrogram']
                      
        t_step = self.params['time_downsample_disp']
        f_step = self.params['freq_downsample_disp']
    
        try:   
            time = self.analyzer.active_song.time[::t_step]
            freq = self.analyzer.active_song.freq[::f_step]
        except AttributeError:
            self.logger.error('No active song, cannot display spectrogram')
            return
            
        try: 
            disp_Sxx = np.flipud(self.analyzer.Sxx[::t_step, ::f_step])
        except AttributeError:
            self.logger.error('No calculated spectrogram, cannot display')
            return
        
        halfbin_time = (time[1] - time[0]) / 2.0
        halfbin_freq = (freq[1] - freq[0]) / 2.0
        
        # this method is much much faster!
        # center bin
        extent = (time[0] - halfbin_time, time[-1] + halfbin_time,
                  freq[0] - halfbin_freq, freq[-1] + halfbin_freq)
        
        self.toolbar.image = ax.imshow(disp_Sxx, 
                interpolation="nearest", 
                extent=extent,
                cmap='gray_r',
                vmin=self.params['vmin'],
                vmax=self.params['vmax']
                )
        
        ax.axis('tight')
  
        self.toolbar.set_range('spectrogram', self.analyzer.active_song.range)        
        self.canvas.draw_idle()
    
    def display_classification(self):
        """Fetches classification data from analyzer and plots it
        
        NO display method affects the domain in any way.  That must be done
        external to the display method
        """
        try:
            ax = self.toolbar.axis_dict['classification']
        except KeyError:
            self.toolbar.add_axis('classification')
            ax = self.toolbar.axis_dict['classification']
            
        try:
            classes = self.analyzer.active_song.classification
            time = self.analyzer.active_song.time
        except AttributeError:
            self.logger.error('No active song to display')
            return
        
        if ax.lines:
            ax.lines.remove(ax.lines[0])
            
        ax.plot(time, classes, 'b-')
        
        self.toolbar.set_range('classification', (0, max(classes)+1))

        self.canvas.draw_idle()
        
    def keyPressEvent(self, e):
        """Listens for a keypress
        
        If the keypress is a number and a region has been selected with the
        select tool, the keypress will assign the value of that number to be
        the classification of the selected region
        """
        if (e.text() in [str(i) for i in range(10)] and 
                self.toolbar.current_selection):
            indices = np.searchsorted(self.analyzer.active_song.time, 
                    np.asarray(self.toolbar.current_selection))
            
            self.analyzer.active_song.classification[indices[0]:indices[1]] = int(e.text())
            
            self.logger.debug('Updating class from %s to be %d', 
                    str(self.analyzer.active_song.time[indices]), int(e.text()))
        
            self.display_classification()
            self.toolbar.remove_rubberband()
            self.toolbar.current_selection = ()
                
                
        
        
class SpectrogramNavBar(NavigationToolbar2QT):
    """Provides a navigation bar specially configured for spectrogram interaction
    
    This class overrides a number of the methods of the standard 
    NavigationToolbar2QT and NavigationToolbar2, and adds some convenience
    methods.
    
    Of primary interest is that this class keeps record of all the axes on the
    plot by name, with independent y scales but a uniform x-scale.  The primary
    intent of this class is to bound the x-scale so that it is impossible to
    scroll, pan, or zoom outside of the domain set in the public instance
    variable x_constraint.  
    
    Additionally, the navigation bar tools have been updated.  The left and 
    right buttons scroll left and right, rather than moving between views.  The 
    pan and zoom buttons are identical, but with the horizontal bound enforced.  
    Several buttons are removed, and a 'select' button has been added which
    is used for manual classification of data.
    """
    
    
    def __init__(self, canvas_, parent_, *args, **kwargs):  
        """Creates a SpectrogramNavigationBar instance
        
        This method initializes logging, creates an empty dictionary of axes,
        an empty selection
        """ 
        
        #initialize logging
        self.logger = logging.getLogger('NavBar.logger')
        
        #A single, unified set of x-boundaries, never violable
        self.x_constraint = ()
        #Dictionary mapping str->axis object
        self.axis_dict = {}
        #Ordered list of axis names, in order added
        self.axis_names = []
        
        self.current_selection = ()
        self.playback = 0
        
        self.image = None
            
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
        
        self.custom_toolitems = (
            (None, None, None, None),
            ('Select', 'Cursor with click, select with drag', 'select1', 'select'),
        )
                
        self.icons_dir = os.path.join(os.path.dirname(__file__), 'icons')
        self.logger.debug('Icons directory %s', self.icons_dir)
        
        NavigationToolbar2QT.__init__(self, canvas_, parent_, coordinates=False)

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
         
        self.locLabel = QtWidgets.QLabel("", self)
        labelAction = self.addWidget(self.locLabel)
        labelAction.setVisible(True) 
        self.coordinates = True
                    
        self._idSelect = None
   
    def local_icon(self, name):
        imagefile = os.path.join(self.icons_dir, name)
        
        self.logger.debug('Icon image file %s', imagefile)
        return QtGui.QIcon(imagefile)
         
    def add_axis(self, name, init_x=(), init_y=()):
        """Add one axis to this plot, and associate it with name"""
        
        if not self.axis_dict:
            self.axis_dict[name] = self.canvas.figure.add_subplot(111)
            self.axis_names.append(name)
            if init_x:
                self.set_domain(init_x)
            if init_y:
                self.set_range(name, init_y)
        else:
            self.axis_dict[name] = self.axis_dict[self.axis_names[0]].twinx()
            self.axis_names.append(name)
            if init_y:
                self.set_range(name, init_y)
                
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
            
        self.dynamic_update()
    
    def set_range(self, name, y_range):
        """Set the y-axis range of the plot associated with name"""
        
        try:
            ax = self.axis_dict[name]
        except KeyError:
            self.logger.warning('No such axis to set the range')
            return
        
        self.logger.debug('Setting the range of %s to %s', name, str(y_range))
        ax.set_ylim(y_range)
        
        self.dynamic_update()
    
    def set_all_ranges(self, yranges):
        """Set the range (y-axis) of all plots linked to this NavBar"""
        
        try:
            for idx, yrange in enumerate(yranges):
                self.set_range(self.axis_names[idx], yrange)
        except IndexError:
            self.logger.warning('Too many yranges provided, there are only %d' 
                    'axes available', len(self.axis_names)+1)
            return

    def forward(self, *args):
        """OVERRIDE the foward function in backend_bases.NavigationToolbar2
        
        Scrolls right
        """
        
        self.logger.debug('Clicked the forward button')
        
        self.remove_rubberband()
        self.current_selection = ()
        
        try:
            ax = self.axis_dict[self.axis_names[0]]
        except IndexError:
            self.logger.warning("Scrolling irrelevant, no plots at this time")
        else:
            xbounds = ax.get_xlim()
            width = xbounds[1] - xbounds[0]
            if xbounds[1]+0.25*width <= self.x_constraint[1]:
                dx = 0.25*width
            else:
                dx = self.x_constraint[1] - xbounds[1]
                
            new_bounds = (xbounds[0]+dx, xbounds[1]+dx)
            
            self.set_domain(new_bounds)
     
    def back(self, *args):
        """OVERRIDE the back function in backend_bases.NavigationToolbar2
        
        Scrolls left
        """
        
        self.logger.debug('Clicked the back button')
        
        self.remove_rubberband()
        self.current_selection = ()
        
        try:
            ax = self.axis_dict[self.axis_names[0]]
        except IndexError:
            self.logger.warning("Scrolling irrelevant, no plots at this time")
        else:
            xbounds = ax.get_xlim()
            width = xbounds[1] - xbounds[0]
            if xbounds[0]-0.25*width >= self.x_constraint[0]:
                dx = 0.25*width
            else:
                dx = xbounds[0] - self.x_constraint[0]
                
            new_bounds = (xbounds[0]-dx, xbounds[1]-dx)
            
            self.set_domain(new_bounds)        
     
    def home(self, *args):
        save_dict = {}
        for name, ax in self.axis_dict.items():
            if name != 'spectrogram':
                save_dict[name] = ax.get_ylim()
                
        super(SpectrogramNavBar, self).home(*args) 
         
        for name, lim in save_dict.items():
            self.set_range(name, lim) 
            
    def drag_pan(self, event):
        """OVERRIDE the drag_pan function in backend_bases.NavigationToolbar2
        
        Adjusted to make sure limits are maintained
        """
        
        for a, _ in self._xypress:
            #safer to use the recorded button at the press than current button:
            #multiple buttons can get pressed during motion...
            pre_drag_x = a.get_xlim()
            pre_drag_y = a.get_ylim()
            a.drag_pan(self._button_pressed, event.key, event.x, event.y)
            
            if not self.valid(a.get_xlim()):
                self.set_domain(pre_drag_x)
                
            if a is not self.axis_dict['spectrogram']:
                a.set_ylim(pre_drag_y)
            
        self.dynamic_update()

    def pan(self, *args):
        self.remove_rubberband()
        self.current_selection = ()
        super(SpectrogramNavBar, self).pan(*args)
        
    def zoom(self, *args):
        self.remove_rubberband()
        self.current_selection = ()
        super(SpectrogramNavBar, self).zoom(*args)
        
    def release_zoom(self, event):
        """OVERRIDE the release_zoom method in backend_bases.NavigationToolbar2
        
        Identical function with domain checking added
        """
        
        self.logger.debug('Called release_zoom')
        
        for zoom_id in self._ids_zoom:
            self.canvas.mpl_disconnect(zoom_id)
        self._ids_zoom = []

        self.remove_rubberband()

        if not self._xypress:
            return

        x, y = event.x, event.y
        lastx, lasty, _, _, _ = self._xypress[0]
        
        try:
            a = self.axis_dict['spectrogram']
        except KeyError:
            self.logger.warning('No plots, no zooming')
            return
        # ignore singular clicks - 5 pixels is a threshold
        # allows the user to "cancel" a zoom action
        # by zooming by less than 5 pixels
        if ((abs(x - lastx) < 5 and self._zoom_mode!="y") or
                (abs(y - lasty) < 5 and self._zoom_mode!="x")):
            
            if self._button_pressed == 1:
                direction = 'in'
                
            elif self._button_pressed == 3:
                direction = 'out'
            
            
            self._xypress = None
            self.release(event)
            self.draw()
            return

        if self._button_pressed == 1:
            direction = 'in'
        elif self._button_pressed == 3:
            direction = 'out'

        a._set_view_from_bbox((lastx, lasty, x, y), direction,
                              self._zoom_mode, False, False)
        
        if not self.valid(a.get_xlim()):
            self.set_domain(self.validate(a.get_xlim()))

        self.draw()
        self._xypress = None
        self._button_pressed = None

        self._zoom_mode = None

        self.push_current()
        self.release(event)    
    
    def _update_buttons_checked(self):
        # sync button checkstates to match active mode
        super(SpectrogramNavBar, self)._update_buttons_checked()
        self._actions['select'].setChecked(self._active == 'SELECT')
    
    def select(self, *args):
        self.logger.debug('Clicked the select button on the toolbar')
        
        """Activate the select tool. select with left button, set cursor with right"""
        # set the pointer icon and button press funcs to the
        # appropriate callbacks

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

        #for a in self.canvas.figure.get_axes():
        #    a.set_navigate_mode(self._active)

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
        self._select_start = event.xdata

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
    
    def release_select(self, event):
        self.logger.debug('Released mouse in select mode')
        
        self.canvas.mpl_disconnect(self._idSelect)
        self._idSelect = None

        if not self._xypress:
            return

        lastx, lasty, _, _, _ = self._xypress[0]
    
        if self._button_pressed == 3:
            self.playback = event.xdata
            self.logger.debug('Playback marker set to %0.4f', self.playback)
        
        elif self._button_pressed == 1:
            # ignore singular clicks - 5 pixels is a threshold
            # allows the user to "cancel" a selection action
            # by selecting by less than 5 pixels
            if (abs(event.x - lastx) < 5 and abs(event.y - lasty) < 5):
                
                self.current_selection = ()
                
            else:
                if event.xdata > self._select_start:
                    self.current_selection = (self._select_start, event.xdata)
                else:
                    self.current_selection = (event.xdata, self._select_start)
                
                
                self.playback = self.current_selection[0]  
                self.logger.debug('Selection set to %s and playback marker to %0.4f', 
                        str(self.current_selection), self.playback)

        self.draw()
        self._xypress = None
        self._button_pressed = None

        self.release(event)
    
    def drag_select(self, event):
        
        if self._button_pressed == 3:
            return 
        elif self._button_pressed == 1:
            if self._xypress:
                x, y = event.x, event.y
                lastx, lasty, a, _, _ = self._xypress[0]
    
                # adjust x, last, y, last
                x1, y1, x2, y2 = a.bbox.extents
                x, lastx = max(min(x, lastx), x1), min(max(x, lastx), x2)
                y, lasty = max(min(y, lasty), y1), min(max(y, lasty), y2)
    
                self.draw_rubberband(event, x, y, lastx, lasty)
        
    def _set_cursor(self, event):
        """OVERRIDE the _set_cursor method in backend_bases.NavigationToolbar2"""
        
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
    
    def valid(self, xlims):
        if not xlims:
            return False
        if not self.x_constraint:
            return True
        else:
            return xlims[0] >= self.x_constraint[0] and xlims[1] <= self.x_constraint[1]
        
    def validate(self, xlims):
        if self.valid(xlims):
            return xlims
        else:
            return (max(xlims[0], self.x_constraint[0]), min(xlims[1], self.x_constraint[1]))
        
        
        
class OutLog:
    '''OutLog pipes output from a stream to a QTextEdit widget
    
    This class is taken exactly from stackoverflow
    http://stackoverflow.com/questions/17132994/pyside-and-python-logging/17145093#17145093
    '''
    
    
    def __init__(self, edit, out=None, color=None):
        """(edit, out=None, color=None) -> can write stdout, stderr to a
        QTextEdit.
        edit = QTextEdit
        out = alternate stream ( can be the original sys.stdout )
        color = alternate color (i.e. color stderr a different color)
        """
        self.edit = edit
        self.out = None
        self.color = color

    def write(self, m):
        if self.color:
            tc = self.edit.textColor()
            self.edit.setTextColor(self.color)

        self.edit.moveCursor(QtGui.QTextCursor.End)
        self.edit.insertPlainText( m )

        if self.color:
            self.edit.setTextColor(tc)

        if self.out:
            self.out.write(m)
            
    def flush(self):
        pass
 
           
def main():    
    app = QtGui.QApplication(sys.argv)
    main = AudioGUI()
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
