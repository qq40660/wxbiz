"""Classes for running EIPC Devices in the background."""

#-----------------------------------------------------------------------------
# Imports
#-----------------------------------------------------------------------------

import time
from threading import Thread
try:
    from multiprocessing import Process
except ImportError:
    Process = None

from eipc.kernel import device, Context

#-----------------------------------------------------------------------------
# Classes
#-----------------------------------------------------------------------------

class Device:
    """A Threadsafe EIPC Device.
    
    *Warning* as with most 'threadsafe' Python objects, this is only
    threadsafe as long as you do not use private methods or attributes.
    Private names are prefixed with '_', such as ``self._setup_socket()``.
    
    For thread safety, you do not pass Sockets to this, but rather Socket
    types::

        Device(device_type, in_socket_type, out_socket_type)

    For instance::

        dev = Device(eipc.QUEUE, eipc.DEALER, eipc.ROUTER)

    Similar to eipc.device, but socket types instead of sockets themselves are
    passed, and the sockets are created in the work thread, to avoid issues
    with thread safety. As a result, additional bind_{in|out} and
    connect_{in|out} methods and setsockopt_{in|out} allow users to specify
    connections for the sockets.
    
    Parameters
    ----------
    device_type : int
        The EIPC Device type
    {in|out}_type : int
        eipc socket types, to be passed later to context.socket(). e.g.
        eipc.PUB, eipc.SUB, eipc.REQ. If out_type is < 0, then in_socket is used
        for both in_socket and out_socket.
        
    Methods
    -------
    bind_{in_out}(iface)
        passthrough for ``{in|out}_socket.bind(iface)``, to be called in the thread
    connect_{in_out}(iface)
        passthrough for ``{in|out}_socket.connect(iface)``, to be called in the
        thread
    setsockopt_{in_out}(opt,value)
        passthrough for ``{in|out}_socket.setsockopt(opt, value)``, to be called in
        the thread
    
    Attributes
    ----------
    daemon : int
        sets whether the thread should be run as a daemon
        Default is true, because if it is false, the thread will not
        exit unless it is killed
    context_factory : callable (class attribute)
        Function for creating the Context. This will be Context.intance
        in ThreadDevices, and Context in ProcessDevices.  The only reason
        it is not instance() in ProcessDevices is that there may be a stale
        Context instance already initialized, and the forked environment
        should *never* try to use it.
    """
    
    context_factory = Context.instance

    def __init__(self, device_type, in_type, out_type):
        self.device_type = device_type
        self.in_type = in_type
        self.out_type = out_type
        self._in_binds = list()
        self._in_connects = list()
        self._in_sockopts = list()
        self._out_binds = list()
        self._out_connects = list()
        self._out_sockopts = list()
        self.daemon = True
        self.done = False
    
    def bind_in(self, addr):
        """Enqueue EIPC address for binding on in_socket.

        See eipc.Socket.bind for details.
        """
        self._in_binds.append(addr)
    
    def connect_in(self, addr):
        """Enqueue EIPC address for connecting on in_socket.

        See eipc.Socket.connect for details.
        """
        self._in_connects.append(addr)
    
    def setsockopt_in(self, opt, value):
        """Enqueue setsockopt(opt, value) for in_socket

        See eipc.Socket.setsockopt for details.
        """
        self._in_sockopts.append((opt, value))
    
    def bind_out(self, iface):
        """Enqueue EIPC address for binding on out_socket.

        See eipc.Socket.bind for details.
        """
        self._out_binds.append(iface)
    
    def connect_out(self, iface):
        """Enqueue EIPC address for connecting on out_socket.

        See eipc.Socket.connect for details.
        """
        self._out_connects.append(iface)
    
    def setsockopt_out(self, opt, value):
        """Enqueue setsockopt(opt, value) for out_socket

        See eipc.Socket.setsockopt for details.
        """
        self._out_sockopts.append((opt, value))
    
    def _setup_sockets(self):
        ctx = self.context_factory()
        
        self._context = ctx
        
        # create the sockets
        ins = ctx.socket(self.in_type)
        if self.out_type < 0:
            outs = ins
        else:
            outs = ctx.socket(self.out_type)
        
        # set sockopts (must be done first, in case of eipc.IDENTITY)
        for opt,value in self._in_sockopts:
            ins.setsockopt(opt, value)
        for opt,value in self._out_sockopts:
            outs.setsockopt(opt, value)
        
        for iface in self._in_binds:
            ins.bind(iface)
        for iface in self._out_binds:
            outs.bind(iface)
        
        for iface in self._in_connects:
            ins.connect(iface)
        for iface in self._out_connects:
            outs.connect(iface)
        
        return ins,outs
    
    def run(self):
        """The runner method.

        Do not call me directly, instead call ``self.start()``, just like a
        Thread.
        """
        ins,outs = self._setup_sockets()
        rc = device(self.device_type, ins, outs)
        self.done = True
        return rc
    
    def start(self):
        """Start the device. Override me in subclass for other launchers."""
        return self.run()

    def join(self,timeout=None):
        """wait for me to finish, like Thread.join.
        
        Reimplemented appropriately by sublcasses."""
        tic = time.time()
        toc = tic
        while not self.done and not (timeout is not None and toc-tic > timeout):
            time.sleep(.001)
            toc = time.time()


class BackgroundDevice(Device):
    """Base class for launching Devices in background processes and threads."""

    launcher=None
    _launch_class=None

    def start(self):
        self.launcher = self._launch_class(target=self.run)
        self.launcher.daemon = self.daemon
        return self.launcher.start()

    def join(self, timeout=None):
        return self.launcher.join(timeout=timeout)


class ThreadDevice(BackgroundDevice):
    """A Device that will be run in a background Thread.

    See Device for details.
    """
    _launch_class=Thread

class ProcessDevice(BackgroundDevice):
    """A Device that will be run in a background Process.

    See Device for details.
    """
    _launch_class=Process
    context_factory = Context


__all__ = [ 'Device', 'ThreadDevice']
if Process is not None:
    __all__.append('ProcessDevice')
