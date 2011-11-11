#-------------------------------------------------------------------------------
# Name:        kdetools
# Purpose:
#
# Author:      pab
#
# Created:     01.11.2008
# Copyright:   (c) pab 2008
# Licence:     LGPL
#-------------------------------------------------------------------------------
#!/usr/bin/env python
from __future__ import division
from itertools import product
from misc import tranproc #, trangood
from numpy import pi, sqrt, atleast_2d, exp, newaxis #@UnresolvedImport
from scipy import interpolate, linalg
from scipy.special import gamma
from wafo.misc import meshgrid
from wafo.wafodata import WafoData

import copy
import numpy as np
import scipy
import warnings
import pylab

_stats_epan = (1. / 5, 3. / 5, np.inf)
_stats_biwe = (1. / 7, 5. / 7, 45. / 2)
_stats_triw = (1. / 9, 350. / 429, np.inf)
_stats_rect = (1. / 3, 1. / 2, np.inf)
_stats_tria = (1. / 6, 2. / 3, np.inf)
_stats_lapl = (2, 1. / 4, np.inf)
_stats_logi = (pi ** 2 / 3, 1. / 6, 1 / 42)
_stats_gaus = (1, 1. / (2 * sqrt(pi)), 3. / (8 * sqrt(pi)))
              
__all__ = ['sphere_volume', 'TKDE', 'KDE', 'Kernel', 'accum', 'qlevels',
           'iqrange', 'gridcount', 'kde_demo1', 'kde_demo2', 'test_docstrings']
def sphere_volume(d, r=1.0):
    """
    Returns volume of  d-dimensional sphere with radius r

    Parameters
    ----------
    d : scalar or array_like
        dimension of sphere
    r : scalar or array_like
        radius of sphere (default 1)
        
    Example
    -------
    >>> sphere_volume(2., r=2.)
    12.566370614359172
    >>> sphere_volume(2., r=1.)
    3.1415926535897931

    Reference
    ---------
    Wand,M.P. and Jones, M.C. (1995)
    'Kernel smoothing'
    Chapman and Hall, pp 105
    """
    return (r ** d) * 2.0 * pi ** (d / 2.0) / (d * gamma(d / 2.0))

class _KDE(object):
    """ Kernel-Density Estimator base class.

    Parameters
    ----------
    data : (# of dims, # of data)-array
        datapoints to estimate from
    hs : array-like (optional) 
        smooting parameter vector/matrix.
        (default compute from data using kernel.get_smoothing function)
    kernel :  kernel function object.
        kernel must have get_smoothing method
    alpha : real scalar (optional)
        sensitivity parameter               (default 0 regular KDE)
        A good choice might be alpha = 0.5 ( or 1/D)
        alpha = 0      Regular  KDE (hs is constant)
        0 < alpha <= 1 Adaptive KDE (Make hs change)  


    Members
    -------
    d : int
        number of dimensions
    n : int
        number of datapoints

    Methods
    -------
    kde.eval_grid_fast(x0, x1,..., xd) : array
        evaluate the estimated pdf on meshgrid(x0, x1,..., xd)
    kde.eval_grid(x0, x1,..., xd) : array
        evaluate the estimated pdf on meshgrid(x0, x1,..., xd)
    kde.eval_points(points) : array
        evaluate the estimated pdf on a provided set of points
    kde(x0, x1,..., xd) : array
        same as kde.eval_grid(x0, x1,..., xd)
    """

    def __init__(self, data, hs=None, kernel=None, alpha=0.0, xmin=None, xmax=None, inc=128):
        self.dataset = atleast_2d(data)
        self.hs = hs
        self.kernel = kernel if kernel else Kernel('gauss')
        self.alpha = alpha
        self.xmin = xmin
        self.xmax = xmax
        self.inc = inc
        self.initialize()

    def initialize(self):
        self.d, self.n = self.dataset.shape
        self._set_xlimits()
        self._initialize()
        
    def _initialize(self):
        pass
    
    def _set_xlimits(self):
        amin = self.dataset.min(axis= -1)
        amax = self.dataset.max(axis= -1)
        iqr = iqrange(self.dataset, axis= -1)
        sigma = np.minimum(np.std(self.dataset, axis= -1, ddof=1), iqr / 1.34)
        #xyzrange = amax - amin
        #offset = xyzrange / 4.0
        offset = 2 * sigma
        if self.xmin is None:
            self.xmin = amin - offset
        else:
            self.xmin = self.xmin * np.ones(self.d)
        if self.xmax is None:
            self.xmax = amax + offset
        else:
            self.xmax = self.xmax * np.ones(self.d)
            
    def eval_grid_fast(self, *args, **kwds):
        """Evaluate the estimated pdf on a grid.

        Parameters
        ----------
        arg_0,arg_1,... arg_d-1 : vectors
            Alternatively, if no vectors is passed in then
             arg_i = linspace(self.xmin[i], self.xmax[i], self.inc)

        Returns
        -------
        values : array-like
            The values evaluated at meshgrid(*args).

        """
        return self._eval_grid_fun(self._eval_grid_fast, *args, **kwds)
       
    def _eval_grid_fast(self, *args):
        pass
    
    def eval_grid(self, *args, **kwds):
        """Evaluate the estimated pdf on a grid.

        Parameters
        ----------
        arg_0,arg_1,... arg_d-1 : vectors
            Alternatively, if no vectors is passed in then
             arg_i = linspace(self.xmin[i], self.xmax[i], self.inc)
        output : string
            'value' if value output
            'wafodata' if object output
        
        Returns
        -------
        values : array-like
            The values evaluated at meshgrid(*args).

        """
        return self._eval_grid_fun(self._eval_grid, *args, **kwds)
    def _eval_grid(self, *args):
        pass
    def _eval_grid_fun(self, eval_grd, *args, **kwds):
        if len(args) == 0:
            args = []
            for i in range(self.d):
                args.append(np.linspace(self.xmin[i], self.xmax[i], self.inc))
        self.args = args
        f = eval_grd(*args)
        if kwds.get('output', 'value') == 'value':
            return f
        else:
            titlestr = 'Kernel density estimate (%s)' % self.kernel.name
            kwds2 = dict(title=titlestr)
            kwds2.update(**kwds)
            if self.d == 1:
                args = args[0]
            elif self.d > 1:
                PL = np.r_[10:90:20, 95, 99, 99.9]
                ql = qlevels(f, p=PL)
                kwds2.setdefault('levels', ql)
            return WafoData(f, args, **kwds2)

    def _check_shape(self, points):
        points = atleast_2d(points)
        d, m = points.shape
        if d != self.d:
            if d == 1 and m == self.d:
                # points was passed in as a row vector
                points = np.reshape(points, (self.d, 1))
            else:
                msg = "points have dimension %s, dataset has dimension %s" % (d,
                    self.d)
                raise ValueError(msg)
        return points   
    def eval_points(self, points):
        """Evaluate the estimated pdf on a set of points.

        Parameters
        ----------
        points : (# of dimensions, # of points)-array
            Alternatively, a (# of dimensions,) vector can be passed in and
            treated as a single point.

        Returns
        -------
        values : (# of points,)-array
            The values at each point.

        Raises
        ------
        ValueError if the dimensionality of the input points is different than
        the dimensionality of the KDE.
        """

        points = self._check_shape(points)
        return self._eval_points(points)
    
    def _eval_points(self, points):
        pass

    __call__ = eval_grid
    
class TKDE(_KDE):
    """ Transformation Kernel-Density Estimator.

    Parameters
    ----------
    dataset : (# of dims, # of data)-array
        datapoints to estimate from
    hs : array-like (optional) 
        smooting parameter vector/matrix.
        (default compute from data using kernel.get_smoothing function)
    kernel :  kernel function object.
        kernel must have get_smoothing method
    alpha : real scalar (optional)
        sensitivity parameter               (default 0 regular KDE)
        A good choice might be alpha = 0.5 ( or 1/D)
        alpha = 0      Regular  KDE (hs is constant)
        0 < alpha <= 1 Adaptive KDE (Make hs change)
    xmin, xmax  : vectors 
        specifying the default argument range for the kde.eval_grid methods. 
        For the kde.eval_grid_fast methods the values must cover the range of the data. 
        (default min(data)-range(data)/4, max(data)-range(data)/4)
        If a single value of xmin or xmax is given then the boundary is the is 
        the same for all dimensions.
    inc :  scalar integer
        defining the default dimension of the output from kde.eval_grid methods (default 128)
        (For kde.eval_grid_fast: A value below 50 is very fast to compute but 
        may give some inaccuracies. Values between 100 and 500 give very 
        accurate results)  
    L2 : array-like 
        vector of transformation parameters (default 1 no transformation)
        t(xi;L2) = xi^L2*sign(L2)   for L2(i) ~= 0
        t(xi;L2) = log(xi)          for L2(i) == 0 
        If single value of L2 is given then the transformation is the same in all directions.
        
    Members
    -------
    d : int
        number of dimensions
    n : int
        number of datapoints

    Methods
    -------
    kde.eval_grid_fast(x0, x1,..., xd) : array
        evaluate the estimated pdf on meshgrid(x0, x1,..., xd)
    kde.eval_grid(x0, x1,..., xd) : array
        evaluate the estimated pdf on meshgrid(x0, x1,..., xd)
    kde.eval_points(points) : array
        evaluate the estimated pdf on a provided set of points
    kde(x0, x1,..., xd) : array
        same as kde.eval_grid(x0, x1,..., xd)
   
    
    Example
    -------
    N = 20
    data = np.random.rayleigh(1, size=(N,))
    >>> data = np.array([ 0.75355792,  0.72779194,  0.94149169,  0.07841119,  2.32291887,
    ...        1.10419995,  0.77055114,  0.60288273,  1.36883635,  1.74754326,
    ...        1.09547561,  1.01671133,  0.73211143,  0.61891719,  0.75903487,
    ...        1.8919469 ,  0.72433808,  1.92973094,  0.44749838,  1.36508452])

    >>> import wafo.kdetools as wk
    >>> x = np.linspace(0.01, max(data.ravel()) + 1, 10)  
    >>> kde = wk.TKDE(data, hs=0.5, L2=0.5)
    >>> f = kde(x)
    >>> f
    array([ 1.03982714,  0.45839018,  0.39514782,  0.32860602,  0.26433318,
            0.20717946,  0.15907684,  0.1201074 ,  0.08941027,  0.06574882])
            
    >>> kde.eval_grid(x)
    array([ 1.03982714,  0.45839018,  0.39514782,  0.32860602,  0.26433318,
            0.20717946,  0.15907684,  0.1201074 ,  0.08941027,  0.06574882])
            
    >>> kde.eval_grid_fast(x)
    array([ 1.06437223,  0.46203314,  0.39593137,  0.32781899,  0.26276433,
            0.20532206,  0.15723498,  0.11843998,  0.08797755,  0.        ])
            
    import pylab as plb          
    h1 = plb.plot(x, f) #  1D probability density plot
    t = np.trapz(f, x)   
    """

    def __init__(self, data, hs=None, kernel=None, alpha=0.0, xmin=None,
                 xmax=None, inc=128, L2=None):
        self.L2 = L2
        _KDE.__init__(self, data, hs, kernel, alpha, xmin, xmax, inc)
    
    def _initialize(self):
        self._check_xmin()
        tdataset = self._dat2gaus(self.dataset)
        xmin = self.xmin
        if xmin is not None:
            xmin = self._dat2gaus(xmin)
        xmax = self.xmax
        if xmax is not None:
            xmax = self._dat2gaus(xmax)
        self.tkde = KDE(tdataset, self.hs, self.kernel, self.alpha, xmin, xmax,
                       self.inc)
    def _check_xmin(self):
        if self.L2 is not None:
            amin = self.dataset.min(axis= -1)
            L2 = np.atleast_1d(self.L2) * np.ones(self.d) # default no transformation
            self.xmin = np.where(L2 != 1, np.maximum(self.xmin, amin / 100.0), self.xmin)
            
    def _dat2gaus(self, points):
        if self.L2 is None:
            return points # default no transformation
        
        L2 = np.atleast_1d(self.L2) * np.ones(self.d) # default no transformation
        
        tpoints = copy.copy(points)
        for i, v2 in enumerate(L2.tolist()):
            tpoints[i] = np.log(points[i]) if v2 == 0 else points[i] ** v2
        return tpoints
    
    def _gaus2dat(self, tpoints):
        if self.L2 is None:
            return tpoints # default no transformation
        
        L2 = np.atleast_1d(self.L2) * np.ones(self.d) # default no transformation
        
        points = copy.copy(tpoints)
        for i, v2 in enumerate(L2.tolist()):
            points[i] = np.exp(tpoints[i]) if v2 == 0 else tpoints[i] ** (1.0 / v2)
        return points
    
    def _scale_pdf(self, pdf, points):
        if self.L2 is None:
            return pdf
        L2 = np.atleast_1d(self.L2) * np.ones(self.d) # default no transformation
        for i, v2 in enumerate(L2.tolist()):
            factor = v2 * np.sign(v2) if v2 else 1
            pdf *= np.where(v2 == 1, 1, points[i] ** (v2 - 1) * factor)
        if (np.abs(np.diff(pdf)).max() > 10).any():
            msg = ''' Numerical problems may have occured due to the power
                    transformation. Check the KDE for spurious spikes'''
            warnings.warn(msg)
        return pdf
    
    def eval_grid_fast2(self, *args, **kwds):
        """Evaluate the estimated pdf on a grid.
        
        Parameters
        ----------
        arg_0,arg_1,... arg_d-1 : vectors
           Alternatively, if no vectors is passed in then
            arg_i = gauss2dat(linspace(dat2gauss(self.xmin[i]), dat2gauss(self.xmax[i]), self.inc))
        
        Returns
        -------
        values : array-like
           The values evaluated at meshgrid(*args).
        
        """
        f = self._eval_grid_fast(*args)
        if kwds.get('output', 'value') == 'value':
            return f
        else:
            args = self.args
            titlestr = 'Kernel density estimate (%s)' % self.kernel.name
            kwds2 = dict(title=titlestr)
            kwds2.update(**kwds)
            if self.d == 1:
                args = args[0]        
            return WafoData(f, args, **kwds2)
    
    def _eval_grid_fast(self, *args): 
        if self.L2 is None:
            f = self.tkde.eval_grid_fast(*args)
            self.args = self.tkde.args
            return f
        #targs = self._dat2gaus(list(args)) if len(args) else args
        tf = self.tkde.eval_grid_fast()
        self.args = self._gaus2dat(list(self.tkde.args))
        points = meshgrid(*self.args) if self.d > 1 else self.args
        f = self._scale_pdf(tf, points)
        if len(args):
            if self.d == 1:
                pdf = interpolate.interp1d(points[0], f, bounds_error=False, fill_value=0.0)
            elif self.d == 2:
                pdf = interpolate.interp2d(points[0], points[1], f, bounds_error=False, fill_value=0.0)
            #ipoints = meshgrid(*args) if self.d>1 else args
            fi = pdf(*args)
            self.args = args
            #fi.shape = ipoints[0].shape
            return fi
        return f
    def _eval_grid(self, *args):
        if self.L2 is None:
            return self.tkde.eval_grid(*args)
        targs = self._dat2gaus(list(args))
        tf = self.tkde.eval_grid(*targs)
        points = meshgrid(*args) if self.d > 1 else self.args
        f = self._scale_pdf(tf, points)
        return f

    def _eval_points(self, points):
        """Evaluate the estimated pdf on a set of points.

        Parameters
        ----------
        points : (# of dimensions, # of points)-array
            Alternatively, a (# of dimensions,) vector can be passed in and
            treated as a single point.

        Returns
        -------
        values : (# of points,)-array
            The values at each point.

        Raises
        ------
        ValueError if the dimensionality of the input points is different than
        the dimensionality of the KDE.
        """
        if self.L2 is None:
            return self.tkde.eval_points(points)
        
        tpoints = self._dat2gaus(points)
        tf = self.tkde.eval_points(tpoints)
        f = self._scale_pdf(tf, points)
        return f
    
class KDE(_KDE):
    """ Kernel-Density Estimator.

    Parameters
    ----------
    data : (# of dims, # of data)-array
        datapoints to estimate from
    hs : array-like (optional) 
        smooting parameter vector/matrix.
        (default compute from data using kernel.get_smoothing function)
    kernel :  kernel function object.
        kernel must have get_smoothing method
    alpha : real scalar (optional)
        sensitivity parameter               (default 0 regular KDE)
        A good choice might be alpha = 0.5 ( or 1/D)
        alpha = 0      Regular  KDE (hs is constant)
        0 < alpha <= 1 Adaptive KDE (Make hs change)  
    xmin, xmax  : vectors 
        specifying the default argument range for the kde.eval_grid methods. 
        For the kde.eval_grid_fast methods the values must cover the range of the data. 
        (default min(data)-range(data)/4, max(data)-range(data)/4)
        If a single value of xmin or xmax is given then the boundary is the is 
        the same for all dimensions.
    inc :  scalar integer
        defining the default dimension of the output from kde.eval_grid methods (default 128)
        (For kde.eval_grid_fast: A value below 50 is very fast to compute but 
        may give some inaccuracies. Values between 100 and 500 give very 
        accurate results)  

    Members
    -------
    d : int
        number of dimensions
    n : int
        number of datapoints

    Methods
    -------
    kde.eval_grid_fast(x0, x1,..., xd) : array
        evaluate the estimated pdf on meshgrid(x0, x1,..., xd)
    kde.eval_grid(x0, x1,..., xd) : array
        evaluate the estimated pdf on meshgrid(x0, x1,..., xd)
    kde.eval_points(points) : array
        evaluate the estimated pdf on a provided set of points
    kde(x0, x1,..., xd) : array
        same as kde.eval_grid(x0, x1,..., xd)
   
    
    Example
    -------
    N = 20
    data = np.random.rayleigh(1, size=(N,))
    >>> data = np.array([ 0.75355792,  0.72779194,  0.94149169,  0.07841119,  2.32291887,
    ...        1.10419995,  0.77055114,  0.60288273,  1.36883635,  1.74754326,
    ...        1.09547561,  1.01671133,  0.73211143,  0.61891719,  0.75903487,
    ...        1.8919469 ,  0.72433808,  1.92973094,  0.44749838,  1.36508452])

    >>> x = np.linspace(0, max(data.ravel()) + 1, 10) 
    >>> import wafo.kdetools as wk 
    >>> kde = wk.KDE(data, hs=0.5, alpha=0.5)
    >>> f = kde(x)
    >>> f
    array([ 0.17252055,  0.41014271,  0.61349072,  0.57023834,  0.37198073,
            0.21409279,  0.12738463,  0.07460326,  0.03956191,  0.01887164])
    
    >>> kde.eval_grid(x)
    array([ 0.17252055,  0.41014271,  0.61349072,  0.57023834,  0.37198073,
            0.21409279,  0.12738463,  0.07460326,  0.03956191,  0.01887164])
    
    >>> kde0 = wk.KDE(data, hs=0.5, alpha=0.0)
    >>> kde0.eval_points(x)
    array([ 0.2039735 ,  0.40252503,  0.54595078,  0.52219649,  0.3906213 ,
            0.26381501,  0.16407362,  0.08270612,  0.02991145,  0.00720821])
    
    >>> kde0.eval_grid(x)
    array([ 0.2039735 ,  0.40252503,  0.54595078,  0.52219649,  0.3906213 ,
            0.26381501,  0.16407362,  0.08270612,  0.02991145,  0.00720821])
    >>> f = kde0.eval_grid(x, output='plotobj')
    >>> f.data
    array([ 0.2039735 ,  0.40252503,  0.54595078,  0.52219649,  0.3906213 ,
            0.26381501,  0.16407362,  0.08270612,  0.02991145,  0.00720821])
            
    >>> f = kde0.eval_grid_fast()
    >>> np.interp(x, kde0.args[0], f)
    array([ 0.21227584,  0.41256459,  0.5495661 ,  0.5176579 ,  0.38431616,
            0.2591162 ,  0.15978948,  0.07889179,  0.02769818,  0.00791829])
    >>> f1 = kde0.eval_grid_fast(output='plot')
    >>> np.interp(x, f1.args, f1.data)
    array([ 0.21227584,  0.41256459,  0.5495661 ,  0.5176579 ,  0.38431616,
            0.2591162 ,  0.15978948,  0.07889179,  0.02769818,  0.00791829])
    >>> h = f1.plot()
        
    import pylab as plb          
    h1 = plb.plot(x, f) #  1D probability density plot
    t = np.trapz(f, x)   
    """

    def __init__(self, data, hs=None, kernel=None, alpha=0.0, xmin=None, xmax=None, inc=128):
        _KDE.__init__(self, data, hs, kernel, alpha, xmin, xmax, inc)
            
    def _initialize(self):
        self._compute_smoothing()
        if self.alpha > 0:
            pilot = KDE(self.dataset, hs=self.hs, kernel=self.kernel, alpha=0)
            f = pilot.eval_points(self.dataset) # get a pilot estimate by regular KDE (alpha=0)
            g = np.exp(np.mean(np.log(f)))
            self._lambda = (f / g) ** (-self.alpha)
        else:
            self._lambda = np.ones(self.n)
                
    def _compute_smoothing(self):
        """Computes the smoothing matrix
        """
        get_smoothing = self.kernel.get_smoothing
        h = self.hs
        if h is None:
            h = get_smoothing(self.dataset)
        h = np.atleast_1d(h)
        hsiz = h.shape
    
        if (len(hsiz) == 1) or (self.d == 1):
            if max(hsiz) == 1:
                h = h * np.ones(self.d)
            else:
                h.shape = (self.d,) # make sure it has the correct dimension
          
            # If h negative calculate automatic values
            ind, = np.where(h <= 0)
            for i in ind.tolist(): # 
                h[i] = get_smoothing(self.dataset[i])
            deth = h.prod()
            self.inv_hs = linalg.diag(1.0 / h)
        else: #fully general smoothing matrix
            deth = linalg.det(h)
            if deth <= 0:
                raise ValueError('bandwidth matrix h must be positive definit!')
            self.inv_hs = linalg.inv(h)
        self.hs = h
        self._norm_factor = deth * self.n
    

    def _eval_grid_fast(self, *args):
        # TODO: This does not work correctly yet! Check it.
        X = np.vstack(args)
        d, inc = X.shape
        dx = X[:, 1] - X[:, 0]
        
        Xn = []
        nfft0 = 2 * inc
        nfft = (nfft0,)*d
        x0 = np.linspace(-inc, inc, nfft0 + 1)
        for i in range(d):
            Xn.append(x0[:-1] * dx[i])
        
        Xnc = meshgrid(*Xn) if d > 1 else Xn
        
        shape0 = Xnc[0].shape
        for i in range(d):
            Xnc[i].shape = (-1,)
 
        Xn = np.dot(self.inv_hs, np.vstack(Xnc))
        
        # Obtain the kernel weights.        
        kw = self.kernel(Xn) / (self._norm_factor * self.kernel.norm_factor(d, self.n))
        kw.shape = shape0
        kw = np.fft.ifftshift(kw)
        fftn = np.fft.fftn
        ifftn = np.fft.ifftn

        # Find the binned kernel weights, c.
        c = gridcount(self.dataset, X)

        # Perform the convolution.
        z = np.real(ifftn(fftn(c, s=nfft) * fftn(kw)))

        ix = (slice(0, inc),)*d
        return z[ix] * (z[ix] > 0.0)
   
    def _eval_grid(self, *args):
        
        grd = meshgrid(*args) if len(args) > 1 else list(args)
        shape0 = grd[0].shape
        d = len(grd)
        for i in range(d):
            grd[i] = grd[i].ravel()
        f = self.eval_points(np.vstack(grd))
        return f.reshape(shape0)
    

    def _eval_points(self, points):
        """Evaluate the estimated pdf on a set of points.

        Parameters
        ----------
        points : (# of dimensions, # of points)-array
            Alternatively, a (# of dimensions,) vector can be passed in and
            treated as a single point.

        Returns
        -------
        values : (# of points,)-array
            The values at each point.

        Raises
        ------
        ValueError if the dimensionality of the input points is different than
        the dimensionality of the KDE.
        """
        d, m = points.shape
       
        result = np.zeros((m,))

        if m >= self.n:
            # there are more points than data, so loop over data
            for i in range(self.n):
                diff = self.dataset[:, i, np.newaxis] - points
                tdiff = np.dot(self.inv_hs / self._lambda[i], diff)
                result += self.kernel(tdiff) / self._lambda[i] ** d
        else:
            # loop over points
            for i in range(m):
                diff = self.dataset - points[:, i, np.newaxis]
                tdiff = np.dot(self.inv_hs, diff / self._lambda[np.newaxis, :])
                tmp = self.kernel(tdiff) / self._lambda ** d
                result[i] = tmp.sum(axis= -1)

        result /= (self._norm_factor * self.kernel.norm_factor(d, self.n))

        return result

    
class _Kernel(object):
    def __init__(self, r=1.0, stats=None):
        self.r = r # radius of kernel
        self.stats = stats
    def norm_factor(self, d=1, n=None):
        return 1.0
    def norm_kernel(self, x):
        X = np.atleast_2d(x)
        return self._kernel(X) / self.norm_factor(*X.shape)
    def kernel(self, x):
        return self._kernel(np.atleast_2d(x))
    def deriv4_6_8_10(self, t, numout=4):
        raise Exception('Method not implemented for this kernel!')
    def effective_support(self):
        '''
        Return the effective support of kernel.
        
        The kernel must be symmetric and compactly supported on [-tau tau]
        if the kernel has infinite support then the kernel must have 
        the effective support in [-tau tau], i.e., be negligible outside the range
        '''
        return self._effective_support()
    def _effective_support(self):
        return - self.r, self.r
    __call__ = kernel 
    
class _KernelMulti(_Kernel):
    # p=0;  %Sphere = rect for 1D
    # p=1;  %Multivariate Epanechnikov kernel.
    # p=2;  %Multivariate Bi-weight Kernel
    # p=3;  %Multi variate Tri-weight Kernel 
    # p=4;  %Multi variate Four-weight Kernel
    def __init__(self, r=1.0, p=1, stats=None):
        self.r = r
        self.p = p
        self.stats = stats
    def norm_factor(self, d=1, n=None):
        r = self.r
        p = self.p
        c = 2 ** p * np.prod(np.r_[1:p + 1]) * sphere_volume(d, r) / np.prod(np.r_[(d + 2):(2 * p + d + 1):2])# normalizing constant
        return c
    def _kernel(self, x):
        r = self.r
        p = self.p
        x2 = x ** 2
        return ((1.0 - x2.sum(axis=0) / r ** 2).clip(min=0.0)) ** p

mkernel_epanechnikov = _KernelMulti(p=1, stats=_stats_epan)
mkernel_biweight = _KernelMulti(p=2, stats=_stats_biwe)
mkernel_triweight = _KernelMulti(p=3, stats=_stats_triw)

class _KernelProduct(_KernelMulti):
    # p=0;  %rectangular
    # p=1;  %1D product Epanechnikov kernel.
    # p=2;  %1D product Bi-weight Kernel
    # p=3;  %1D product Tri-weight Kernel 
    # p=4;  %1D product Four-weight Kernel
    
    def norm_factor(self, d=1, n=None):
        r = self.r
        p = self.p
        c = 2 ** p * np.prod(np.r_[1:p + 1]) * sphere_volume(1, r) / np.prod(np.r_[(1 + 2):(2 * p + 2):2])# normalizing constant
        return c ** d
    def _kernel(self, x):
        r = self.r # radius
        pdf = (1 - (x / r) ** 2).clip(min=0.0)
        return pdf.prod(axis=0)

mkernel_p1epanechnikov = _KernelProduct(p=1, stats=_stats_epan)
mkernel_p1biweight = _KernelProduct(p=2, stats=_stats_biwe)
mkernel_p1triweight = _KernelProduct(p=3, stats=_stats_triw)


class _KernelRectangular(_Kernel):
    def _kernel(self, x):
        return np.where(np.all(np.abs(x) <= self.r, axis=0), 1, 0.0)
    def norm_factor(self, d=1, n=None):
        r = self.r
        return (2 * r) ** d
mkernel_rectangular = _KernelRectangular(stats=_stats_rect)

class _KernelTriangular(_Kernel):
    def _kernel(self, x):
        pdf = (1 - np.abs(x)).clip(min=0.0)
        return pdf.prod(axis=0)
mkernel_triangular = _KernelTriangular(stats=_stats_tria)
    
class _KernelGaussian(_Kernel):
    def _kernel(self, x):
        sigma = self.r / 4.0
        x2 = (x / sigma) ** 2
        return exp(-0.5 * x2.sum(axis=0))       
    def norm_factor(self, d=1, n=None):
        sigma = self.r / 4.0
        return (2 * pi * sigma) ** (d / 2.0) 
    def deriv4_6_8_10(self, t, numout=4):
        '''
        Returns 4th, 6th, 8th and 10th derivatives of the kernel function.
        '''
        phi0 = exp(-0.5 * t ** 2) / sqrt(2 * pi)
        p4 = [1, 0, -6, 0, +3]
        p4val = np.polyval(p4, t) * phi0
        if numout == 1:
            return p4val
        out = [p4val]
        pn = p4
        for unusedix in range(numout - 1):
            pnp1 = np.polyadd(-np.r_[pn, 0], np.polyder(pn))
            pnp2 = np.polyadd(-np.r_[pnp1, 0], np.polyder(pnp1))
            out.append(np.polyval(pnp2, t) * phi0)
            pn = pnp2
        return out
    
mkernel_gaussian = _KernelGaussian(r=4.0, stats=_stats_gaus)

#def mkernel_gaussian(X):
#    x2 = X ** 2
#    d = X.shape[0]
#    return (2 * pi) ** (-d / 2) * exp(-0.5 * x2.sum(axis=0))       

class _KernelLaplace(_Kernel):
    def _kernel(self, x):
        absX = np.abs(x)    
        return exp(-absX.sum(axis=0))
    def norm_factor(self, d=1, n=None):
        return 2 ** d    
mkernel_laplace = _KernelLaplace(r=7.0, stats=_stats_lapl)

class _KernelLogistic(_Kernel):
    def _kernel(self, x):
        s = exp(-x)
        return np.prod(1.0 / (s + 1) ** 2, axis=0)
mkernel_logistic = _KernelLogistic(r=7.0, stats=_stats_logi)

_MKERNEL_DICT = dict(
                     epan=mkernel_epanechnikov,
                     biwe=mkernel_biweight,
                     triw=mkernel_triweight,
                     p1ep=mkernel_p1epanechnikov,
                     p1bi=mkernel_p1biweight,
                     p1tr=mkernel_p1triweight,
                     rect=mkernel_rectangular,
                     tria=mkernel_triangular,
                     lapl=mkernel_laplace,
                     logi=mkernel_logistic,
                     gaus=mkernel_gaussian
                     )
_KERNEL_EXPONENT_DICT = dict(re=0, sp=0, ep=1, bi=2, tr=3, fo=4, fi=5, si=6, se=7)

class Kernel(object):
    '''
    Multivariate kernel
    
    Parameters
    ----------
    name : string
        defining the kernel. Valid options are:
        'epanechnikov'  - Epanechnikov kernel. 
        'biweight'      - Bi-weight kernel.
        'triweight'     - Tri-weight kernel.
        'p1epanechnikov' - product of 1D Epanechnikov kernel. 
        'p1biweight'    - product of 1D Bi-weight kernel.
        'p1triweight'   - product of 1D Tri-weight kernel.
        'triangular'    - Triangular kernel.
        'gaussian'      - Gaussian kernel
        'rectangular'   - Rectangular kernel. 
        'laplace'       - Laplace kernel.
        'logistic'      - Logistic kernel.
    Note that only the first 4 letters of the kernel name is needed.
    
    Examples
    --------
     N = 20
    data = np.random.rayleigh(1, size=(N,))
    >>> data = np.array([ 0.75355792,  0.72779194,  0.94149169,  0.07841119,  2.32291887,
    ...        1.10419995,  0.77055114,  0.60288273,  1.36883635,  1.74754326,
    ...        1.09547561,  1.01671133,  0.73211143,  0.61891719,  0.75903487,
    ...        1.8919469 ,  0.72433808,  1.92973094,  0.44749838,  1.36508452])
    
    >>> import wafo.kdetools as wk
    >>> gauss = wk.Kernel('gaussian')
    >>> gauss.stats()  
    (1, 0.28209479177387814, 0.21157109383040862)
    >>> gauss.hscv(data)
    array([ 0.21555043])
    >>> gauss.hstt(data)
    array([ 0.15165387])
    >>> gauss.hste(data)
    array([ 0.18942238])
    >>> gauss.hldpi(data)
    array([ 0.1718688])
    
    >>> wk.Kernel('laplace').stats()
    (2, 0.25, inf)
    
    >>> triweight = wk.Kernel('triweight'); triweight.stats()
    (0.1111111111111111, 0.81585081585081587, inf)
    
    >>> triweight(np.linspace(-1,1,11))
    array([ 0.      ,  0.046656,  0.262144,  0.592704,  0.884736,  1.      ,
            0.884736,  0.592704,  0.262144,  0.046656,  0.      ])
    >>> triweight.hns(data)
    array([ 0.82087056])
    >>> triweight.hos(data)
    array([ 0.88265652])
    >>> triweight.hste(data)
    array([ 0.56570278])
    >>> triweight.hscv(data)
    array([ 0.64193201])
    
    See also
    --------
    mkernel
    
    References
    ---------- 
    B. W. Silverman (1986) 
    'Density estimation for statistics and data analysis'  
     Chapman and Hall, pp. 43, 76 
     
    Wand, M. P. and Jones, M. C. (1995) 
    'Density estimation for statistics and data analysis'  
     Chapman and Hall, pp 31, 103,  175  
    '''
    def __init__(self, name, fun='hns'):
        self.kernel = _MKERNEL_DICT[name[:4]]
        #self.name = self.kernel.__name__.replace('mkernel_', '').title()
        try:
            self.get_smoothing = getattr(self, fun) 
        except:
            self.get_smoothing = self.hns
    def _get_name(self):
        return self.kernel.__class__.__name__.replace('_Kernel', '').title()
    name = property(_get_name)
    def stats(self):
        ''' Return some 1D statistics of the kernel.
      
        Returns
        ------- 
        mu2 : real scalar 
            2'nd order moment, i.e.,int(x^2*kernel(x))
        R : real scalar
            integral of squared kernel, i.e., int(kernel(x)^2)
        Rdd  : real scalar
            integral of squared double derivative of kernel, i.e., int( (kernel''(x))^2 ).
                  
        Reference
        --------- 
        Wand,M.P. and Jones, M.C. (1995) 
        'Kernel smoothing'
        Chapman and Hall, pp 176.
        '''  
        return self.kernel.stats
        #name = self.name[2:6] if self.name[:2].lower() == 'p1' else self.name[:4] 
        #return _KERNEL_STATS_DICT[name.lower()]
    def deriv4_6_8_10(self, t, numout=4):
        return self.kernel.deriv4_6_8_10(t, numout)
    
    def effective_support(self):
        return self.kernel.effective_support()
    
    def hns(self, data):
        '''
        Returns Normal Scale Estimate of Smoothing Parameter.
        
        Parameter
        ---------
        data : 2D array
            shape d x n (d = # dimensions )
        
        Returns
        -------
        h : array-like
            one dimensional optimal value for smoothing parameter
            given the data and kernel.  size D
         
        HNS only gives an optimal value with respect to mean integrated 
        square error, when the true underlying distribution 
        is Gaussian. This works reasonably well if the data resembles a
        Gaussian distribution. However if the distribution is asymmetric,
        multimodal or have long tails then HNS may  return a to large
        smoothing parameter, i.e., the KDE may be oversmoothed and mask
        important features of the data. (=> large bias).
        One way to remedy this is to reduce H by multiplying with a constant 
        factor, e.g., 0.85. Another is to try different values for H and make a 
        visual check by eye.
        
        Example: 
          data = rndnorm(0, 1,20,1)
          h = hns(data,'epan');
        
        See also:
        ---------  
        hste, hbcv, hboot, hos, hldpi, hlscv, hscv, hstt, kde
        
        Reference:  
        ---------
        B. W. Silverman (1986) 
        'Density estimation for statistics and data analysis'  
        Chapman and Hall, pp 43-48 
        Wand,M.P. and Jones, M.C. (1995) 
        'Kernel smoothing'
        Chapman and Hall, pp 60--63
        '''
        
        A = np.atleast_2d(data)
        n = A.shape[1]
        
        # R= int(mkernel(x)^2),  mu2= int(x^2*mkernel(x))
        mu2, R, unusedRdd = self.stats()
        AMISEconstant = (8 * sqrt(pi) * R / (3 * mu2 ** 2 * n)) ** (1. / 5)
        iqr = iqrange(A, axis=1) # interquartile range
        stdA = np.std(A, axis=1, ddof=1)
        # use of interquartile range guards against outliers.
        # the use of interquartile range is better if 
        # the distribution is skew or have heavy tails
        # This lessen the chance of oversmoothing.
        return np.where(iqr > 0, np.minimum(stdA, iqr / 1.349), stdA) * AMISEconstant
    
    def hos(self, data):
        ''' Returns Oversmoothing Parameter.

        
        
           h      = one dimensional maximum smoothing value for smoothing parameter
                    given the data and kernel.  size 1 x D
           data   = data matrix, size N x D (D = # dimensions )
         
         The oversmoothing or maximal smoothing principle relies on the fact
         that there is a simple upper bound for the AMISE-optimal bandwidth for
         estimation of densities with a fixed value of a particular scale
         measure. While HOS will give too large bandwidth for optimal estimation 
         of a general density it provides an excellent starting point for
         subjective choice of bandwidth. A sensible strategy is to plot an
         estimate with bandwidth HOS and then sucessively look at plots based on 
         convenient fractions of HOS to see what features are present in the
         data for various amount of smoothing. The relation to HNS is given by:
         
                   HOS = HNS/0.93
        
          Example: 
          data = rndnorm(0, 1,20,1)
          h = hos(data,'epan');
          
         See also  hste, hbcv, hboot, hldpi, hlscv, hscv, hstt, kde, kdefun
        
         Reference
         --------- 
          B. W. Silverman (1986) 
         'Density estimation for statistics and data analysis'  
          Chapman and Hall, pp 43-48 
        
          Wand,M.P. and Jones, M.C. (1986) 
         'Kernel smoothing'
          Chapman and Hall, pp 60--63
        '''    
        return self.hns(data) / 0.93
    def hmns(self, data):
        '''
        Returns Multivariate Normal Scale Estimate of Smoothing Parameter.
        
         CALL:  h = hmns(data,kernel)
        
           h      = M dimensional optimal value for smoothing parameter
                    given the data and kernel.  size D x D
           data   = data matrix, size D x N (D = # dimensions )
           kernel = 'epanechnikov'  - Epanechnikov kernel.
                    'biweight'      - Bi-weight kernel.
                    'triweight'     - Tri-weight kernel.  
                    'gaussian'      - Gaussian kernel
          
          Note that only the first 4 letters of the kernel name is needed.
         
         HMNS  only gives  a optimal value with respect to mean integrated 
         square error, when the true underlying distribution  is
         Multivariate Gaussian. This works reasonably well if the data resembles a
         Multivariate Gaussian distribution. However if the distribution is 
         asymmetric, multimodal or have long tails then HNS is maybe more 
         appropriate.
        
          Example: 
            data = rndnorm(0, 1,20,2)
            h = hmns(data,'epan');
          
         See also 
         --------
          
        hns, hste, hbcv, hboot, hos, hldpi, hlscv, hscv, hstt
        
         Reference
         ----------  
          B. W. Silverman (1986) 
         'Density estimation for statistics and data analysis'  
          Chapman and Hall, pp 43-48, 87 
        
          Wand,M.P. and Jones, M.C. (1995) 
         'Kernel smoothing'
          Chapman and Hall, pp 60--63, 86--88
        '''
        # TODO: implement more kernels  
          
        A = np.atleast_2d(data)
        d, n = A.shape
        
        if d == 1:
            return self.hns(data)
        name = self.name[:4].lower()
        if name == 'epan':        # Epanechnikov kernel
            a = (8.0 * (d + 4.0) * (2 * sqrt(pi)) ** d / sphere_volume(d)) ** (1. / (4.0 + d))
        elif name == 'biwe': # Bi-weight kernel
            a = 2.7779;
            if d > 2:
                raise ValueError('not implemented for d>2')
        elif name == 'triw': # Triweight
            a = 3.12;
            if d > 2:
                raise ValueError('not implemented for d>2')
        elif name == 'gaus': # Gaussian kernel
            a = (4.0 / (d + 2.0)) ** (1. / (d + 4.0))
        else:
            raise ValueError('Unknown kernel.')
         
        covA = scipy.cov(A)
        
        return a * linalg.sqrtm(covA) * n * (-1. / (d + 4))
    def hste(self, data, h0=None, inc=128, maxit=100, releps=0.01, abseps=0.0):
        '''HSTE 2-Stage Solve the Equation estimate of smoothing parameter.
        
         CALL:  hs = hste(data,kernel,h0)
         
               hs = one dimensional value for smoothing parameter
                    given the data and kernel.  size 1 x D
           data   = data matrix, size N x D (D = # dimensions )
           kernel = 'gaussian'  - Gaussian kernel (default)
                     ( currently the only supported kernel)
               h0 = initial starting guess for hs (default h0=hns(A,kernel))
        
          Example: 
           x  = rndnorm(0,1,50,1);
           hs = hste(x,'gauss');
        
         See also  hbcv, hboot, hos, hldpi, hlscv, hscv, hstt, kde, kdefun
        
         Reference:  
          B. W. Silverman (1986) 
         'Density estimation for statistics and data analysis'  
          Chapman and Hall, pp 57--61
        
          Wand,M.P. and Jones, M.C. (1986) 
         'Kernel smoothing'
          Chapman and Hall, pp 74--75
        '''  
        # TODO: NB: this routine can be made faster:
        # TODO: replace the iteration in the end with a Newton Raphson scheme
        
        A = np.atleast_2d(data)
        d, n = A.shape
        
        # R= int(mkernel(x)^2),  mu2= int(x^2*mkernel(x))
        mu2, R, unusedRdd = self.stats()
        
        AMISEconstant = (8 * sqrt(pi) * R / (3 * mu2 ** 2 * n)) ** (1. / 5)
        STEconstant = R / (mu2 ** (2) * n)
        
        sigmaA = self.hns(A) / AMISEconstant
        if h0 is None:
            h0 = sigmaA * AMISEconstant
        
        h = np.asarray(h0, dtype=float)
       
        nfft = inc * 2 
        amin = A.min(axis=1) # Find the minimum value of A.
        amax = A.max(axis=1) #Find the maximum value of A.
        arange = amax - amin # Find the range of A.
        
        #% xa holds the x 'axis' vector, defining a grid of x values where 
        #% the k.d. function will be evaluated.
        
        ax1 = amin - arange / 8.0
        bx1 = amax + arange / 8.0
        
        kernel2 = Kernel('gauss') 
        mu2, R, unusedRdd = kernel2.stats()
        STEconstant2 = R / (mu2 ** (2) * n)
        fft = np.fft.fft
        ifft = np.fft.ifft
        
        for dim in range(d):
            s = sigmaA[dim]
            ax = ax1[dim]
            bx = bx1[dim]
          
            xa = np.linspace(ax, bx, inc) 
            xn = np.linspace(0, bx - ax, inc)
          
            c = gridcount(A[dim], xa)
       
            # Step 1
            psi6NS = -15 / (16 * sqrt(pi) * s ** 7)
            psi8NS = 105 / (32 * sqrt(pi) * s ** 9)
        
            # Step 2
            k40, k60 = kernel2.deriv4_6_8_10(0, numout=2)
            g1 = (-2 * k40 / (mu2 * psi6NS * n)) ** (1.0 / 7)
            g2 = (-2 * k60 / (mu2 * psi8NS * n)) ** (1.0 / 9)
        
            # Estimate psi6 given g2.
            kw4, kw6 = kernel2.deriv4_6_8_10(xn / g2, numout=2) # kernel weights.
            kw = np.r_[kw6, 0, kw6[-1:0:-1]]             # Apply fftshift to kw.
            z = np.real(ifft(fft(c, nfft) * fft(kw)))     # convolution.
            psi6 = np.sum(c * z[:inc]) / (n * (n - 1) * g2 ** 7)
        
            # Estimate psi4 given g1.
            kw4 = kernel2.deriv4_6_8_10(xn / g1, numout=1) # kernel weights.
            kw = np.r_[kw4, 0, kw4[-1:0:-1]]  #Apply 'fftshift' to kw.
            z = np.real(ifft(fft(c, nfft) * fft(kw))) # convolution.
            psi4 = np.sum(c * z[:inc]) / (n * (n - 1) * g1 ** 5)
        
            
            
            h1 = h[dim]
            h_old = 0
            count = 0
          
            while ((abs(h_old - h1) > max(releps * h1, abseps)) and (count < maxit)):
                count += 1
                h_old = h1
          
                # Step 3
                gamma = ((2 * k40 * mu2 * psi4 * h1 ** 5) / (-psi6 * R)) ** (1.0 / 7)
        
                # Now estimate psi4 given gamma.
                kw4 = kernel2.deriv4_6_8_10(xn / gamma, numout=1) #kernel weights. 
                kw = np.r_[kw4, 0, kw4[-1:0:-1]] # Apply 'fftshift' to kw.
                z = np.real(ifft(fft(c, nfft) * fft(kw))) # convolution.
        
                psi4Gamma = np.sum(c * z[:inc]) / (n * (n - 1) * gamma ** 5)
          
                # Step 4
                h1 = (STEconstant2 / psi4Gamma) ** (1.0 / 5)
            
            # Kernel other than Gaussian scale bandwidth
            h1 = h1 * (STEconstant / STEconstant2) ** (1.0 / 5)
          
        
            if count >= maxit:
                warnings.warn('The obtained value did not converge.')
          
            h[dim] = h1
        #end % for dim loop
        return h
    def hstt(self, data, h0=None, inc=128, maxit=100, releps=0.01, abseps=0.0):
        '''HSTT Scott-Tapia-Thompson estimate of smoothing parameter.
        
         CALL: hs = hstt(data,kernel)
        
               hs = one dimensional value for smoothing parameter
                    given the data and kernel.  size 1 x D
           data   = data matrix, size N x D (D = # dimensions )
           kernel = 'epanechnikov'  - Epanechnikov kernel. (default)
                    'biweight'      - Bi-weight kernel.
                    'triweight'     - Tri-weight kernel.  
                    'triangular'    - Triangular kernel.
                    'gaussian'      - Gaussian kernel
                    'rectangular'   - Rectangular kernel. 
                    'laplace'       - Laplace kernel.
                    'logistic'      - Logistic kernel.  
        
         HSTT returns Scott-Tapia-Thompson (STT) estimate of smoothing
         parameter. This is a Solve-The-Equation rule (STE).
         Simulation studies shows that the STT estimate of HS
         is a good choice under a variety of models. A comparison with
         likelihood cross-validation (LCV) indicates that LCV performs slightly
         better for short tailed densities.
         However, STT method in contrast to LCV is insensitive to outliers.
         
          Example: 
           x  = rndnorm(0,1,50,1);
           hs = hstt(x,'gauss');
        
         See also  hste, hbcv, hboot, hos, hldpi, hlscv, hscv, kde, kdebin 
        
        
        
         Reference:  
          B. W. Silverman (1986) 
         'Density estimation for statistics and data analysis'  
          Chapman and Hall, pp 57--61 
        '''
        A = np.atleast_2d(data)
        d, n = A.shape
        
        # R= int(mkernel(x)^2),  mu2= int(x^2*mkernel(x))
        mu2, R, unusedRdd = self.stats()
        
        AMISEconstant = (8 * sqrt(pi) * R / (3 * mu2 ** 2 * n)) ** (1. / 5)
        STEconstant = R / (mu2 ** (2) * n)
        
        sigmaA = self.hns(A) / AMISEconstant
        if h0 is None:
            h0 = sigmaA * AMISEconstant
        
        h = np.asarray(h0, dtype=float)
       
        nfft = inc * 2 
        amin = A.min(axis=1) # Find the minimum value of A.
        amax = A.max(axis=1) #Find the maximum value of A.
        arange = amax - amin # Find the range of A.
        
        #% xa holds the x 'axis' vector, defining a grid of x values where 
        #% the k.d. function will be evaluated.
        
        ax1 = amin - arange / 8.0
        bx1 = amax + arange / 8.0
        
        fft = np.fft.fft
        ifft = np.fft.ifft
        for dim in range(d):
            s = sigmaA[dim]
            datan = A[dim] / s
            ax = ax1[dim] / s
            bx = bx1[dim] / s
          
            xa = np.linspace(ax, bx, inc) 
            xn = np.linspace(0, bx - ax, inc)
          
            c = gridcount(datan, xa)
            
            count = 1
            h_old = 0
            h1 = h[dim] / s
            delta = (bx - ax) / (inc - 1)
            while ((abs(h_old - h1) > max(releps * h1, abseps)) and (count < maxit)):
                count += 1
                h_old = h1
          
                kw4 = self.kernel(xn / h1) / (n * h1 * self.norm_factor(d=1))  
                kw = np.r_[kw4, 0, kw4[-1:0:-1]] # Apply 'fftshift' to kw.
                f = np.real(ifft(fft(c, nfft) * fft(kw))) # convolution.
               
                #  Estimate psi4=R(f'') using simple finite differences and quadrature.
                ix = np.arange(1, inc - 1)
                z = ((f[ix + 1] - 2 * f[ix] + f[ix - 1]) / delta ** 2) ** 2
                psi4 = delta * z.sum()
                h1 = (STEconstant / psi4) ** (1 / 5);
            
            if count >= maxit:
                warnings.warn('The obtained value did not converge.')
          
            h[dim] = h1 * s
        #end % for dim loop
        return h
            

    def hscv(self, data, hvec=None, inc=128, maxit=100):
        '''
        HSCV Smoothed cross-validation estimate of smoothing parameter.
        
         CALL: [hs,hvec,score] = hscv(data,kernel,hvec); 
         
           hs     = smoothing parameter
           hvec   = vector defining possible values of hs
                     (default linspace(0.25*h0,h0,100), h0=0.62)
           score  = score vector
           data   = data vector
           kernel = 'gaussian'      - Gaussian kernel the only supported
                                       
          Note that only the first 4 letters of the kernel name is needed.
          
          Example: 
            data = rndnorm(0,1,20,1)
             [hs hvec score] = hscv(data,'epan');
             plot(hvec,score) 
         See also  hste, hbcv, hboot, hos, hldpi, hlscv, hstt, kde, kdefun
        
         Wand,M.P. and Jones, M.C. (1986) 
         'Kernel smoothing'
          Chapman and Hall, pp 75--79
        '''
        # TODO: Add support for other kernels than Gaussian  
        A = np.atleast_2d(data)
        d, n = A.shape
        
        # R= int(mkernel(x)^2),  mu2= int(x^2*mkernel(x))
        mu2, R, unusedRdd = self.stats()
        
        AMISEconstant = (8 * sqrt(pi) * R / (3 * mu2 ** 2 * n)) ** (1. / 5)
        STEconstant = R / (mu2 ** (2) * n)
        
        sigmaA = self.hns(A) / AMISEconstant
        if hvec is None:
            H = AMISEconstant / 0.93
            hvec = np.linspace(0.25 * H, H, maxit)
        hvec = np.asarray(hvec, dtype=float)
  
        steps = len(hvec)
        score = np.zeros(steps)

        nfft = inc * 2 
        amin = A.min(axis=1) # Find the minimum value of A.
        amax = A.max(axis=1) #Find the maximum value of A.
        arange = amax - amin # Find the range of A.
        
        #% xa holds the x 'axis' vector, defining a grid of x values where 
        #% the k.d. function will be evaluated.
        
        ax1 = amin - arange / 8.0
        bx1 = amax + arange / 8.0
        
        kernel2 = Kernel('gauss') 
        mu2, R, unusedRdd = kernel2.stats()
        STEconstant2 = R / (mu2 ** (2) * n)
        fft = np.fft.fft
        ifft = np.fft.ifft
        
         
        h = np.zeros(d)
        hvec = hvec * (STEconstant2 / STEconstant) ** (1. / 5.)
        
        k40, k60, k80, k100 = kernel2.deriv4_6_8_10(0, numout=4)
        psi8 = 105 / (32 * sqrt(pi));
        psi12 = 3465. / (512 * sqrt(pi))
        g1 = (-2. * k60 / (mu2 * psi8 * n)) ** (1. / 9.)       
        g2 = (-2. * k100 / (mu2 * psi12 * n)) ** (1. / 13.)
        
        for dim in range(d):
            s = sigmaA[dim]
            ax = ax1[dim] / s
            bx = bx1[dim] / s
            datan = A[dim] / s

            xa = np.linspace(ax, bx, inc) 
            xn = np.linspace(0, bx - ax, inc)
          
            c = gridcount(datan, xa)
       
            kw4, kw6 = kernel2.deriv4_6_8_10(xn / g1, numout=2) 
            kw = np.r_[kw6, 0, kw6[-1:0:-1]]             
            z = np.real(ifft(fft(c, nfft) * fft(kw)))     
            psi6 = np.sum(c * z[:inc]) / (n ** 2 * g1 ** 7)
            
            kw4, kw6, kw8, kw10 = kernel2.deriv4_6_8_10(xn / g2, numout=4) 
            kw = np.r_[kw10, 0, kw10[-1:0:-1]]  
            z = np.real(ifft(fft(c, nfft) * fft(kw)))
            psi10 = np.sum(c * z[:inc]) / (n ** 2 * g2 ** 11)
           
            g3 = (-2. * k40 / (mu2 * psi6 * n)) ** (1. / 7.)
            g4 = (-2. * k80 / (mu2 * psi10 * n)) ** (1. / 11.)
            
            kw4 = kernel2.deriv4_6_8_10(xn / g3, numout=1) 
            kw = np.r_[kw4, 0, kw4[-1:0:-1]]
            z = np.real(ifft(fft(c, nfft) * fft(kw))) 
            psi4 = np.sum(c * z[:inc]) / (n ** 2 * g3 ** 5) 
            
            kw4, kw6, kw8 = kernel2.deriv4_6_8_10(xn / g3, numout=3) 
            kw = np.r_[kw8, 0, kw8[-1:0:-1]]
            z = np.real(ifft(fft(c, nfft) * fft(kw)))
            psi8 = np.sum(c * z[:inc]) / (n ** 2 * g4 ** 9) 
  
            const = (441. / (64 * pi)) ** (1. / 18.) * (4 * pi) ** (-1. / 5.) * psi4 ** (-2. / 5.) * psi8 ** (-1. / 9.)
  
            M = np.atleast_2d(datan) 
  
            Y = (M - M.T).ravel()
  
            for i in range(steps):
                g = const * n ** (-23. / 45) * hvec[i] ** (-2)
                sig1 = sqrt(2 * hvec[i] ** 2 + 2 * g ** 2)
                sig2 = sqrt(hvec[i] ** 2 + 2 * g ** 2)
                sig3 = sqrt(2 * g ** 2)
                term2 = np.sum(kernel2(Y / sig1) / sig1 - 2 * kernel2(Y / sig2) / sig2 + kernel2(Y / sig3) / sig3)
    
                score[i] = 1. / (n * hvec[i] * 2. * sqrt(pi)) + term2 / n ** 2
    
            idx = score.argmin()
            # Kernel other than Gaussian scale bandwidth
            h[dim] = hvec[idx] * (STEconstant / STEconstant2) ** (1 / 5)
            if idx == 0:
                warnings.warn('Optimum is probably lower than hs=%g for dim=%d' % (h[dim] * s, dim))
            elif idx == maxit - 1:
                warnings.warn('Optimum is probably higher than hs=%g for dim=%d' % (h[dim] * s, dim))
            
        hvec = hvec * (STEconstant / STEconstant2) ** (1 / 5)
        return h * sigmaA
    
    def hldpi(self, data, L=2, inc=128):
        '''HLDPI L-stage Direct Plug-In estimate of smoothing parameter.
        
         CALL: hs = hldpi(data,kernel,L)
        
               hs = one dimensional value for smoothing parameter
                    given the data and kernel.  size 1 x D
           data   = data matrix, size N x D (D = # dimensions )
           kernel = 'epanechnikov'  - Epanechnikov kernel.
                    'biweight'      - Bi-weight kernel.
                    'triweight'     - Tri-weight kernel.
                    'triangluar'    - Triangular kernel.
                    'gaussian'      - Gaussian kernel
                    'rectangular'   - Rectanguler kernel.
                    'laplace'       - Laplace kernel.
                    'logistic'      - Logistic kernel.
                L = 0,1,2,3,...   (default 2)
        
          Note that only the first 4 letters of the kernel name is needed.
        
          Example:
           x  = rndnorm(0,1,50,1);
           hs = hldpi(x,'gauss',1);
        
         See also  hste, hbcv, hboot, hos, hlscv, hscv, hstt, kde, kdefun
        
          Wand,M.P. and Jones, M.C. (1995)
         'Kernel smoothing'
          Chapman and Hall, pp 67--74
        '''
        A = np.atleast_2d(data)
        d, n = A.shape
        
        # R= int(mkernel(x)^2),  mu2= int(x^2*mkernel(x))
        mu2, R, unusedRdd = self.stats()
        
        AMISEconstant = (8 * sqrt(pi) * R / (3 * mu2 ** 2 * n)) ** (1. / 5)
        STEconstant = R / (mu2 ** (2) * n)
        
        sigmaA = self.hns(A) / AMISEconstant
        
       
        nfft = inc * 2 
        amin = A.min(axis=1) # Find the minimum value of A.
        amax = A.max(axis=1) #Find the maximum value of A.
        arange = amax - amin # Find the range of A.
        
        #% xa holds the x 'axis' vector, defining a grid of x values where 
        #% the k.d. function will be evaluated.
        
        ax1 = amin - arange / 8.0
        bx1 = amax + arange / 8.0
        
        kernel2 = Kernel('gauss')
        mu2, unusedR, unusedRdd = kernel2.stats()
        
        fft = np.fft.fft
        ifft = np.fft.ifft
        
        h = np.zeros(d)
        for dim in range(d):
            s = sigmaA[dim]
            datan = A[dim] / s
            ax = ax1[dim] / s
            bx = bx1[dim] / s
          
            xa = np.linspace(ax, bx, inc) 
            xn = np.linspace(0, bx - ax, inc)
          
            c = gridcount(datan, xa)
            
            r = 2 * L + 4
            rd2 = L + 2

            # Eq. 3.7 in Wand and Jones (1995)
            PSI_r = (-1) ** (rd2) * np.prod(np.r_[rd2 + 1:r]) / (sqrt(pi) * (2 * s) ** (r + 1));
            PSI = PSI_r
            if L > 0:
                # High order derivatives of the Gaussian kernel
                Kd = kernel2.deriv4_6_8_10(0, numout=L)
    
                # L-stage iterations to estimate PSI_4
                for ix in range(L - 1, -1, -1):
                    gi = (-2 * Kd[ix] / (mu2 * PSI * n)) ** (1. / (2 * ix + 5))

                    # Obtain the kernel weights.
                    KW0 = kernel2.deriv4_6_8_10(xn / gi, numout=ix + 1)
                    if ix > 0:
                        KW0 = KW0[-1]
                    kw = np.r_[KW0, 0, KW0[inc - 1:0:-1]] # Apply 'fftshift' to kw.

                    # Perform the convolution.
                    z = np.real(ifft(fft(c, nfft) * fft(kw)))

                    PSI = np.sum(c * z[:inc]) / (n ** 2 * gi ** (2 * ix + 3))
                    #end
                #end
            h[dim] = s * (STEconstant / PSI) ** (1. / 5)

        return h



    def norm_factor(self, d=1, n=None):
        return  self.kernel.norm_factor(d, n)    
    def eval_points(self, points):
        return self.kernel(np.atleast_2d(points))
    __call__ = eval_points
    
def mkernel(X, kernel):
    '''
    MKERNEL Multivariate Kernel Function.
     
    Paramaters
    ---------  
    X : array-like  
        matrix  size d x n (d = # dimensions, n = # evaluation points)
    kernel : string
        defining kernel
        'epanechnikov'  - Epanechnikov kernel. 
        'biweight'      - Bi-weight kernel.
        'triweight'     - Tri-weight kernel.
        'p1epanechnikov' - product of 1D Epanechnikov kernel. 
        'p1biweight'    - product of 1D Bi-weight kernel.
        'p1triweight'   - product of 1D Tri-weight kernel.
        'triangular'    - Triangular kernel.
        'gaussian'      - Gaussian kernel
        'rectangular'   - Rectangular kernel. 
        'laplace'       - Laplace kernel.
        'logistic'      - Logistic kernel.
    Note that only the first 4 letters of the kernel name is needed.  
    Returns
    -------         
    z : ndarray
        kernel function values evaluated at X
      
    
    See also  
    --------
    kde, kdefun, kdebin
     
    References
    ---------- 
    B. W. Silverman (1986) 
    'Density estimation for statistics and data analysis'  
     Chapman and Hall, pp. 43, 76 
     
    Wand, M. P. and Jones, M. C. (1995) 
    'Density estimation for statistics and data analysis'  
     Chapman and Hall, pp 31, 103,  175  
    '''
    fun = _MKERNEL_DICT[kernel[:4]]
    return fun(np.atleast_2d(X))


def accum(accmap, a, func=None, size=None, fill_value=0, dtype=None):
    """
    An accumulation function similar to Matlab's `accumarray` function.

    Parameters
    ----------
    accmap : ndarray
        This is the "accumulation map".  It maps input (i.e. indices into
        `a`) to their destination in the output array.  The first `a.ndim`
        dimensions of `accmap` must be the same as `a.shape`.  That is,
        `accmap.shape[:a.ndim]` must equal `a.shape`.  For example, if `a`
        has shape (15,4), then `accmap.shape[:2]` must equal (15,4).  In this
        case `accmap[i,j]` gives the index into the output array where
        element (i,j) of `a` is to be accumulated.  If the output is, say,
        a 2D, then `accmap` must have shape (15,4,2).  The value in the
        last dimension give indices into the output array. If the output is
        1D, then the shape of `accmap` can be either (15,4) or (15,4,1) 
    a : ndarray
        The input data to be accumulated.
    func : callable or None
        The accumulation function.  The function will be passed a list
        of values from `a` to be accumulated.
        If None, numpy.sum is assumed.
    size : ndarray or None
        The size of the output array.  If None, the size will be determined
        from `accmap`.
    fill_value : scalar
        The default value for elements of the output array. 
    dtype : numpy data type, or None
        The data type of the output array.  If None, the data type of
        `a` is used.

    Returns
    -------
    out : ndarray
        The accumulated results.

        The shape of `out` is `size` if `size` is given.  Otherwise the
        shape is determined by the (lexicographically) largest indices of
        the output found in `accmap`.


    Examples
    --------
    >>> from numpy import array, prod
    >>> a = array([[1,2,3],[4,-1,6],[-1,8,9]])
    >>> a
    array([[ 1,  2,  3],
           [ 4, -1,  6],
           [-1,  8,  9]])
    >>> # Sum the diagonals.
    >>> accmap = array([[0,1,2],[2,0,1],[1,2,0]])
    >>> s = accum(accmap, a)
    >>> s
    array([ 9,  7, 15])
    >>> # A 2D output, from sub-arrays with shapes and positions like this:
    >>> # [ (2,2) (2,1)]
    >>> # [ (1,2) (1,1)]
    >>> accmap = array([
    ...        [[0,0],[0,0],[0,1]],
    ...        [[0,0],[0,0],[0,1]],
    ...        [[1,0],[1,0],[1,1]]])
    >>> # Accumulate using a product.
    >>> accum(accmap, a, func=prod, dtype=float)
    array([[ -8.,  18.],
           [ -8.,   9.]])
    >>> # Same accmap, but create an array of lists of values.
    >>> accum(accmap, a, func=lambda x: x, dtype='O')
    array([[[1, 2, 4, -1], [3, 6]],
           [[-1, 8], [9]]], dtype=object)
    """

    # Check for bad arguments and handle the defaults.
    if accmap.shape[:a.ndim] != a.shape:
        raise ValueError("The initial dimensions of accmap must be the same as a.shape")
    if func is None:
        func = np.sum
    if dtype is None:
        dtype = a.dtype
    if accmap.shape == a.shape:
        accmap = np.expand_dims(accmap, -1)
    adims = tuple(range(a.ndim))
    if size is None:
        size = 1 + np.squeeze(np.apply_over_axes(np.max, accmap, axes=adims))
    size = np.atleast_1d(size)

    # Create an array of python lists of values.
    vals = np.empty(size, dtype='O')
    for s in product(*[range(k) for k in size]):
        vals[s] = []
    for s in product(*[range(k) for k in a.shape]):
        indx = tuple(accmap[s])
        val = a[s]
        vals[indx].append(val)

    # Create the output array.
    out = np.empty(size, dtype=dtype)
    for s in product(*[range(k) for k in size]):
        if vals[s] == []:
            out[s] = fill_value
        else:
            out[s] = func(vals[s])
    return out

def qlevels(pdf, p=(10, 30, 50, 70, 90, 95, 99, 99.9), x1=None, x2=None):
    '''QLEVELS Calculates quantile levels which encloses P% of PDF
    
      CALL: [ql PL] = qlevels(pdf,PL,x1,x2);
    
            ql    = the discrete quantile levels.
            pdf   = joint point density function matrix or vector
            PL    = percent level (default [10:20:90 95 99 99.9])
            x1,x2 = vectors of the spacing of the variables 
                   (Default unit spacing)
    
    QLEVELS numerically integrates PDF by decreasing height and find the 
    quantile levels which  encloses P% of the distribution. If X1 and 
    (or) X2 is unspecified it is assumed that dX1 and dX2 is constant.
    NB! QLEVELS normalizes the integral of PDF to N/(N+0.001) before 
    calculating QL in order to reflect the sampling of PDF is finite.  
    Currently only able to handle 1D and 2D PDF's if dXi is not constant (i=1,2).
    
    Example
    -------
    >>> import wafo.stats as ws
    >>> x = np.linspace(-8,8,2001);
    >>> PL = np.r_[10:90:20, 90, 95, 99, 99.9]
    >>> qlevels(ws.norm.pdf(x),p=PL, x1=x);
    array([ 0.39591707,  0.37058719,  0.31830968,  0.23402133,  0.10362052,
            0.05862129,  0.01449505,  0.00178806])
            
    # compared with the exact values
    >>> ws.norm.pdf(ws.norm.ppf((100-PL)/200))
    array([ 0.39580488,  0.370399  ,  0.31777657,  0.23315878,  0.10313564,
            0.05844507,  0.01445974,  0.00177719])
       
    See also
    --------
    qlevels2, tranproc
    '''

    norm = 1 # normalize cdf to unity
    pdf = np.atleast_1d(pdf)
    if any(pdf.ravel() < 0):
        raise ValueError('This is not a pdf since one or more values of pdf is negative')
    
    fsiz = pdf.shape
    fsizmin = min(fsiz)
    if fsizmin == 0:
        return []
    
    N = np.prod(fsiz);
    d = len(fsiz)
    if x1 is None or ((x2 is None) and d > 2):
        fdfi = pdf.ravel()
    else:
        if d == 1: # pdf in one dimension
            dx22 = np.ones(1)
        else: # % pdf in two dimensions
            dx2 = np.diff(x2.ravel())*0.5;
            dx22 = np.r_[0, dx2] + np.r_[dx2, 0];
  
        dx1 = np.diff(x1.ravel())*0.5
        dx11 = np.r_[0 , dx1] + np.r_[dx1, 0]
        dx1x2 = dx22[:, None] * dx11
        fdfi = (pdf * dx1x2).ravel();


    p = np.atleast_1d(p)
    
    if np.any((p < 0) | (100 < p)):
        raise ValueError('PL must satisfy 0 <= PL <= 100')

    
    p2 = p / 100.0
    ind = np.argsort(pdf.ravel()) # sort by height of pdf
    ind = ind[::-1]
    fi = pdf.flat[ind]

    Fi = np.cumsum(fdfi[ind]) # integration in the order of decreasing height of pdf
              
    if norm: #  %normalize Fi to make sure int pdf dx1 dx2 approx 1
        Fi = Fi / Fi[-1] * N / (N + 1.5e-8)

    maxFi = np.max(Fi)
    if maxFi > 1:
        warnings.warn('this is not a pdf since cdf>1! normalizing')
        
        Fi = Fi / Fi[-1] * N / (N + 1.5e-8)
    
    elif maxFi < .95:
        msg = '''The given pdf is too sparsely sampled since cdf<.95.  
        Thus QL is questionable'''
        warnings.warn(msg)
    
    ind, = np.where(np.diff(np.r_[Fi, 1]) > 0) # make sure Fi is strictly increasing by not considering duplicate values
    ui = tranproc(Fi[ind], fi[ind], p2) # calculating the inverse of Fi to find the index
    # to the desired quantile level
    # ui=smooth(Fi(ind),fi(ind),1,p2(:),1) % alternative
    # res=ui-ui2

    if np.any(ui >= max(pdf.ravel())):
        warnings.warn('The lowest percent level is too close to 0%')

    if np.any(ui <= min(pdf.ravel())):
        msg = '''The given pdf is too sparsely sampled or
       the highest percent level is too close to 100%'''
        warnings.warn(msg)   
        ui[ui < 0] = 0.0 

    return ui

def qlevels2(data, p=(10,30,50,70,90, 95, 99, 99.9), method=1):
    '''
    QLEVELS2 Calculates quantile levels which encloses P% of data
    
     CALL: [ql PL] = qlevels2(data,PL,method);
    
       ql   = the discrete quantile levels, size D X Np 
    Parameters
    ----------
    data : data matrix, size D x N (D = # of dimensions)
    p : percent level vector, length Np (default [10:20:90 95 99 99.9])
    method : integer
        1 Interpolation so that F(X_(k)) == (k-0.5)/n. (default)
        2 Interpolation so that F(X_(k)) == k/(n+1).
        3 Based on the empirical distribution.
    
    Returns
    -------
    
    QLEVELS2 sort the columns of data in ascending order and find the  
             quantile levels for each column which encloses  P% of the data.  
     
    Examples : % Finding quantile levels enclosing P% of data:
    -------- 
    >>> import wafo.stats as ws
    >>> PL = np.r_[10:90:20, 90, 95, 99, 99.9]
    >>> xs = ws.norm.rvs(size=2500000)
    >>> np.round(qlevels2(ws.norm.pdf(xs), p=PL), decimals=3)
    array([ 0.396,  0.37 ,  0.318,  0.233,  0.103,  0.058,  0.014,  0.002])
            
    # compared with the exact values
    >>> ws.norm.pdf(ws.norm.ppf((100-PL)/200))
    array([ 0.39580488,  0.370399  ,  0.31777657,  0.23315878,  0.10313564,
            0.05844507,  0.01445974,  0.00177719])
           
    # Finding the median of xs:
    >>> '%2.2f' % np.abs(qlevels2(xs,50)[0])
    '0.00'
    
    See also  
    --------
    qlevels
    '''
    q = 100-np.atleast_1d(p)
    return percentile(data, q, axis=-1, method=method)
    

_PKDICT = {1: lambda k, w, n: (k - w) / (n - 1),
           2: lambda k, w, n: (k - w / 2) / n,
           3: lambda k, w, n: k / n,
           4: lambda k, w, n: k / (n + 1),
           5: lambda k, w, n: (k - w / 3) / (n + 1 / 3),
           6: lambda k, w, n: (k - w * 3 / 8) / (n + 1 / 4)}
def _compute_qth_weighted_percentile(a, q, axis, out, method, weights, overwrite_input):
    # normalise weight vector such that sum of the weight vector equals to n
    q = np.atleast_1d(q) / 100.0
    if (q < 0).any() or (q > 1).any():
        raise ValueError, "percentile must be in the range [0,100]"
    
    shape0 = a.shape
    if axis is None:
        sorted = a.ravel()
    else:
        taxes = range(a.ndim) 
        taxes[-1], taxes[axis] = taxes[axis], taxes[-1] 
        sorted = np.transpose(a, taxes).reshape(-1, shape0[axis])
        
    ind = sorted.argsort(axis= -1)
    if overwrite_input:
        sorted.sort(axis= -1)
    else:
        sorted = np.sort(sorted, axis= -1)
     
    w = np.atleast_1d(weights)
    n = len(w)
    w = w * n / w.sum()
    
    # Work on each column separately because of weight vector
    m = sorted.shape[0]
    nq = len(q)
    y = np.zeros((m, nq))
    pk_fun = _PKDICT.get(method, 1)
    for i in range(m):
        sortedW = w[ind[i]]            # rearrange the weight according to ind
        k = sortedW.cumsum()           # cumulative weight
        pk = pk_fun(k, sortedW, n)     # different algorithm to compute percentile
        # Interpolation between pk and sorted for given value of q
        y[i] = np.interp(q, pk, sorted[i])
    if axis is None:
        return np.squeeze(y)
    else:
        shape1 = list(shape0)
        shape1[axis], shape1[-1] = shape1[-1], nq
        return np.squeeze(np.transpose(y.reshape(shape1), taxes))
    
#method=1: p(k) = k/(n-1)
#method=2: p(k) = (k+0.5)/n.
#method=3: p(k) = (k+1)/n
#method=4: p(k) = (k+1)/(n+1)
#method=5: p(k) = (k+2/3)/(n+1/3)
#method=6: p(k) = (k+5/8)/(n+1/4)

_KDICT = {1:lambda p, n: p * (n - 1),
          2:lambda p, n: p * n - 0.5,
          3:lambda p, n: p * n - 1,
          4:lambda p, n: p * (n + 1) - 1,
          5:lambda p, n: p * (n + 1. / 3) - 2. / 3,
          6:lambda p, n: p * (n + 1. / 4) - 5. / 8}
def _compute_qth_percentile(sorted, q, axis, out, method):
    if not np.isscalar(q):
        p = [_compute_qth_percentile(sorted, qi, axis, None, method) 
             for qi in q]
        if out is not None:
            out.flat = p
        return p

    q = q / 100.0
    if (q < 0) or (q > 1):
        raise ValueError, "percentile must be in the range [0,100]"

    indexer = [slice(None)] * sorted.ndim
    Nx = sorted.shape[axis]
    k_fun = _KDICT.get(method, 1)
    index = np.clip(k_fun(q, Nx), 0, Nx - 1)    
    i = int(index)
    if i == index:
        indexer[axis] = slice(i, i + 1)
        weights1 = np.array(1)
        sumval = 1.0
    else:
        indexer[axis] = slice(i, i + 2)
        j = i + 1
        weights1 = np.array([(j - index), (index - i)], float)
        wshape = [1] * sorted.ndim
        wshape[axis] = 2
        weights1.shape = wshape
        sumval = weights1.sum()

    # Use add.reduce in both cases to coerce data type as well as
    # check and use out array.
    return np.add.reduce(sorted[indexer] * weights1, axis=axis, out=out) / sumval

def percentile(a, q, axis=None, out=None, overwrite_input=False, method=1, weights=None):
    """
    Compute the qth percentile of the data along the specified axis.

    Returns the qth percentile of the array elements.

    Parameters
    ----------
    a : array_like
        Input array or object that can be converted to an array.
    q : float in range of [0,100] (or sequence of floats)
        percentile to compute which must be between 0 and 100 inclusive
    axis : {None, int}, optional
        Axis along which the percentiles are computed. The default (axis=None)
        is to compute the median along a flattened version of the array.
    out : ndarray, optional
        Alternative output array in which to place the result. It must
        have the same shape and buffer length as the expected output,
        but the type (of the output) will be cast if necessary.
    overwrite_input : {False, True}, optional
       If True, then allow use of memory of input array (a) for
       calculations. The input array will be modified by the call to
       median. This will save memory when you do not need to preserve
       the contents of the input array. Treat the input as undefined,
       but it will probably be fully or partially sorted. Default is
       False. Note that, if `overwrite_input` is True and the input
       is not already an ndarray, an error will be raised.
    method : scalar integer
        defining the interpolation method. Valid options are
        1 : p[k] = k/(n-1). In this case, p[k] = mode[F(x[k])]. 
                 This is used by S. (default)
        2 : p[k] = (k+0.5)/n. That is a piecewise linear function where
                 the knots are the values midway through the steps of the 
                 empirical cdf. This is popular amongst hydrologists. 
                 Matlab also uses this formula.
        3 : p[k] = (k+1)/n. That is, linear interpolation of the empirical cdf. 
        4 : p[k] = (k+1)/(n+1). Thus p[k] = E[F(x[k])]. 
                 This is used by Minitab and by SPSS. 
        5 : p[k] = (k+2/3)/(n+1/3). Then p[k] =~ median[F(x[k])]. 
                 The resulting quantile estimates are approximately 
                 median-unbiased regardless of the distribution of x. 
        6 : p[k] = (k+5/8)/(n+1/4). The resulting quantile estimates are 
                 approximately unbiased for the expected order statistics 
                 if x is normally distributed.

    Returns
    -------
    pcntile : ndarray
        A new array holding the result (unless `out` is specified, in
        which case that array is returned instead).  If the input contains
        integers, or floats of smaller precision than 64, then the output
        data-type is float64.  Otherwise, the output data-type is the same
        as that of the input.

    See Also
    --------
    mean, median

    Notes
    -----
    Given a vector V of length N, the qth percentile of V is the qth ranked
    value in a sorted copy of V.  A weighted average of the two nearest neighbors
    is used if the normalized ranking does not match q exactly.
    The same as the median if q is 0.5; the same as the min if q is 0;
    and the same as the max if q is 1

    Examples
    --------
    >>> import wafo.kdetools as wk
    >>> a = np.array([[10, 7, 4], [3, 2, 1]])
    >>> a
    array([[10,  7,  4],
           [ 3,  2,  1]])
    >>> wk.percentile(a, 50)
    3.5
    >>> wk.percentile(a, 50, axis=0)
    array([ 6.5,  4.5,  2.5])
    >>> wk.percentile(a, 50, axis=0, weights=np.ones(2))
    array([ 6.5,  4.5,  2.5])
    >>> wk.percentile(a, 50, axis=1)
    array([ 7.,  2.])
    >>> wk.percentile(a, 50, axis=1, weights=np.ones(3))
    array([ 7.,  2.])
    >>> m = wk.percentile(a, 50, axis=0)
    >>> out = np.zeros_like(m)
    >>> wk.percentile(a, 50, axis=0, out=m)
    array([ 6.5,  4.5,  2.5])
    >>> m
    array([ 6.5,  4.5,  2.5])
    >>> b = a.copy()
    >>> wk.percentile(b, 50, axis=1, overwrite_input=True)
    array([ 7.,  2.])
    >>> assert not np.all(a==b)
    >>> b = a.copy()
    >>> wk.percentile(b, 50, axis=None, overwrite_input=True)
    3.5
    >>> np.all(a==b)
    False

    """
    a = np.asarray(a)
    try:
        if q == 0:
            return a.min(axis=axis, out=out)
        elif q == 100:
            return a.max(axis=axis, out=out)
    except:
        pass
    if weights is not None:
        return _compute_qth_weighted_percentile(a, q, axis, out, method, weights, overwrite_input)
    elif overwrite_input:
        if axis is None:
            sorted = a.ravel()
            sorted.sort()
        else:
            a.sort(axis=axis)
            sorted = a
    else:
        sorted = np.sort(a, axis=axis)
    if axis is None:
        axis = 0

    return _compute_qth_percentile(sorted, q, axis, out, method)

def iqrange(data, axis=None):
    '''
    Returns the Inter Quartile Range of data
    
    Parameters
    ----------
    data : array-like
        Input array or object that can be converted to an array.
    axis : {None, int}, optional
        Axis along which the percentiles are computed. The default (axis=None)
        is to compute the median along a flattened version of the array.
    Returns
    -------
    r : array-like
        abs(np.percentile(data, 75, axis)-np.percentile(data, 25, axis))
    
    Notes
    -----    
    IQRANGE is a robust measure of spread. The use of interquartile range 
    guards against outliers if the distribution have heavy tails.
    
    Example
    -------
    >>> a = np.arange(101)
    >>> iqrange(a)
    50.0
    
    See also  
    --------
    np.std
    '''
    return np.abs(np.percentile(data, 75, axis=axis) - np.percentile(data, 25, axis=axis))

def bitget(int_type, offset):
    '''
    Returns the value of the bit at the offset position in int_type.
    
    Example
    -------
    >>> bitget(5, np.r_[0:4])   
    array([1, 0, 1, 0])
    '''
    
    return np.bitwise_and(int_type, 1 << offset) >> offset
    

def gridcount(data, X):
    '''
    Returns D-dimensional histogram using linear binning.
      
    Parameters
    ----------
    data = column vectors with D-dimensional data, size D x Nd 
    X    = row vectors defining discretization, size D x N
            Must include the range of the data.
    
    Returns
    -------
    c    = gridcount,  size N x N x ... x N
             
    GRIDCOUNT obtains the grid counts using linear binning.
    There are 2 strategies: simple- or linear- binning.
    Suppose that an observation occurs at x and that the nearest point
    below and above is y and z, respectively. Then simple binning strategy
    assigns a unit weight to either y or z, whichever is closer. Linear
    binning, on the other hand, assigns the grid point at y with the weight
    of (z-x)/(z-y) and the gridpoint at z a weight of (y-x)/(z-y).
      
    In terms of approximation error of using gridcounts as pdf-estimate,
    linear binning is significantly more accurate than simple binning.  
    
     NOTE: The interval [min(X);max(X)] must include the range of the data.
           The order of C is permuted in the same order as 
           meshgrid for D==2 or D==3.  
       
    Example
    -------
    >>> import numpy as np
    >>> import wafo.kdetools as wk
    >>> import pylab as plb
    >>> N     = 20;
    >>> data  = np.random.rayleigh(1,N)
    >>> x = np.linspace(0,max(data)+1,50)  
    >>> dx = x[1]-x[0]  
    
    >>> c = wk.gridcount(data,x)
    
    >>> h = plb.plot(x,c,'.')   # 1D histogram
    >>> pdf = c/dx/N
    >>> h1 = plb.plot(x, pdf) #  1D probability density plot
    >>> '%1.3f' % np.trapz(pdf, x)   
    '1.000'
    
    See also
    --------
    bincount, accum, kdebin
      
    Reference
    ----------
    Wand,M.P. and Jones, M.C. (1995) 
    'Kernel smoothing'
    Chapman and Hall, pp 182-192  
    '''  
    dat = np.atleast_2d(data)
    x = np.atleast_2d(X)
    d = dat.shape[0]
    d1, inc = x.shape
    
    if d != d1:
        raise ValueError('Dimension 0 of data and X do not match.')
    
    dx = np.diff(x[:, :2], axis=1)
    xlo = x[:, 0]
    xup = x[:, -1]
    
    datlo = dat.min(axis=1)
    datup = dat.max(axis=1)
    if ((datlo < xlo) | (xup < datup)).any():
        raise ValueError('X does not include whole range of the data!')
    
    csiz = np.repeat(inc, d)
    
      
    binx = np.asarray(np.floor((dat - xlo[:, newaxis]) / dx), dtype=int)
    w = dx.prod()
    abs = np.abs
    if  d == 1:
        x.shape = (-1,)
        c = (accum(binx, (x[binx + 1] - dat), size=[inc, ]) + 
             accum(binx, (dat - x[binx]), size=[inc, ])) / w
    elif d == 2:
        b2 = binx[1]
        b1 = binx[0]
        c_ = np.c_
        stk = np.vstack
        c = (accum(c_[b1, b2] , abs(np.prod(stk([X[0, b1 + 1], X[1, b2 + 1]]) - dat, axis=0)), size=[inc, inc]) + 
          accum(c_[b1 + 1, b2]  , abs(np.prod(stk([X[0, b1], X[1, b2 + 1]]) - dat, axis=0)), size=[inc, inc]) + 
          accum(c_[b1  , b2 + 1], abs(np.prod(stk([X[0, b1 + 1], X[1, b2]]) - dat, axis=0)), size=[inc, inc]) + 
          accum(c_[b1 + 1, b2 + 1], abs(np.prod(stk([X[0, b1], X[1, b2]]) - dat, axis=0)), size=[inc, inc])) / w
      
    else: # % d>2
       
        Nc = csiz.prod()
        c = np.zeros((Nc,))
     
        fact2 = np.asarray(np.reshape(inc * np.arange(d), (d, -1)), dtype=int)
        fact1 = np.asarray(np.reshape(csiz.cumprod() / inc, (d, -1)), dtype=int)
        #fact1 = fact1(ones(n,1),:);
        bt0 = [0, 0]
        X1 = X.ravel()
        for ir in xrange(2 ** (d - 1)):
            bt0[0] = np.reshape(bitget(ir, np.arange(d)), (d, -1))
            bt0[1] = 1 - bt0[0]
            for ix in xrange(2):
                one = np.mod(ix, 2)
                two = np.mod(ix + 1, 2)
                # Convert to linear index 
                b1 = np.sum((binx + bt0[one]) * fact1, axis=0) #linear index to c
                bt2 = bt0[two] + fact2
                b2 = binx + bt2                     # linear index to X
                c += accum(b1, abs(np.prod(X1[b2] - dat, axis=0)), size=(Nc,))
                
        c = np.reshape(c / w, csiz, order='C')
        # TODO: check that the flipping of axis is correct
        T = range(d); T[-2], T[-1] = T[-1], T[-2]
        c = c.transpose(*T)

    if d == 2: # make sure c is stored in the same way as meshgrid
        c = c.T
    elif d == 3:
        c = c.transpose(1, 0, 2)
    
    return c


def kde_demo1():
    '''
    KDEDEMO1 Demonstrate the smoothing parameter impact on KDE

    KDEDEMO1 shows the true density (dotted) compared to KDE based on 7
    observations (solid) and their individual kernels (dashed) for 3
    different values of the smoothing parameter, hs.
    '''
    
    import scipy.stats as st
    x = np.linspace(-4, 4)
    x0 = x / 2.0
    data = np.random.normal(loc=0, scale=1.0, size=7) #rndnorm(0,1,7,1);
    kernel = Kernel('gaus')
    hs = kernel.hns(data)
    hVec = [hs / 2, hs, 2 * hs]
       
    for ix, h in enumerate(hVec): 
        pylab.figure(ix)
        kde = KDE(data, hs=h, kernel=kernel)
        f2 = kde(x, output='plot', title='h_s = %2.2f' % h, ylab='Density')
        f2.plot('k-')
       
        pylab.plot(x, st.norm.pdf(x, 0, 1), 'k:')
        n = len(data)
        pylab.plot(data, np.zeros(data.shape), 'bx')
        y = kernel(x0) / (n * h * kernel.norm_factor(d=1, n=n)) 
        for i in range(n):
            pylab.plot(data[i] + x0 * h, y, 'b--')
            pylab.plot([data[i], data[i]], [0, np.max(y)], 'b')
        
        pylab.axis([x.min(), x.max(), 0, 0.5])
     
def kde_demo2(): 
    '''Demonstrate the difference between transformation- and ordinary-KDE

    KDEDEMO2 shows that the transformation KDE is a better estimate for
    Rayleigh distributed data around 0 than the ordinary KDE.
    '''
    import scipy.stats as st
    data = st.rayleigh.rvs(scale=1, size=300)
    
    x = np.linspace(1.5e-3, 5, 55);
    
    kde = KDE(data)
    f = kde(output='plot', title='Ordinary KDE')
    pylab.figure(0)
    f.plot()
    
    
    pylab.plot(x, st.rayleigh.pdf(x, scale=1), ':')
    
    #plotnorm((data).^(L2)) % gives a straight line => L2 = 0.5 reasonable
    
    tkde = TKDE(data, L2=0.5)
    ft = tkde(x, output='plot', title='Transformation KDE')
    pylab.figure(1)
    ft.plot()
    
    pylab.plot(x, st.rayleigh.pdf(x, scale=1), ':')

    pylab.figure(0)
    
def test_docstrings():
    import doctest
    doctest.testmod()
    
if __name__ == '__main__':
    test_docstrings()
    
