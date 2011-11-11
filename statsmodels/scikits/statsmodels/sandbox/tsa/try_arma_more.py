# -*- coding: utf-8 -*-
"""Periodograms for ARMA and time series

theoretical periodogram of ARMA process and different version
of periodogram estimation

uses scikits.talkbox and matplotlib


Created on Wed Oct 14 23:02:19 2009

Author: josef-pktd
"""

import numpy as np
from scipy import signal, ndimage
import matplotlib.mlab as mlb
import matplotlib.pyplot as plt

from scikits.statsmodels.tsa.arima_process import arma_generate_sample, arma_periodogram
from scikits.statsmodels.tsa.stattools import acovf
hastalkbox = False
try:
    import scikits.talkbox as stb
    import scikits.talkbox.spectral.basic as stbs
except:
    hastalkbox = False

ar = [1., -0.7]#[1,0,0,0,0,0,0,-0.7]
ma = [1., 0.3]

ar = np.convolve([1.]+[0]*50 +[-0.6], ar)
ar = np.convolve([1., -0.5]+[0]*49 +[-0.3], ar)

n_startup = 1000
nobs = 1000
# throwing away samples at beginning makes sample more "stationary"

xo = arma_generate_sample(ar,ma,n_startup+nobs)
x = xo[n_startup:]

#moved to tsa.arima_process
#def arma_periodogram(ar, ma, **kwds):
#    '''periodogram for ARMA process given by lag-polynomials ar and ma
#
#    Parameters
#    ----------
#    ar : array_like
#        autoregressive lag-polynomial with leading 1 and lhs sign
#    ma : array_like
#        moving average lag-polynomial with leading 1
#    kwds : options
#        options for scipy.signal.freqz
#        default: worN=None, whole=0
#
#    Returns
#    -------
#    w : array
#        frequencies
#    sd : array
#        periodogram, spectral density
#
#    Notes
#    -----
#    Normalization ?
#
#    '''
#    w, h = signal.freqz(ma, ar, **kwds)
#    sd = np.abs(h)**2/np.sqrt(2*np.pi)
#    if np.sum(np.isnan(h)) > 0:
#        # this happens with unit root or seasonal unit root'
#        print 'Warning: nan in frequency response h'
#    return w, sd

plt.figure()
plt.plot(x)

rescale = 0

w, h = signal.freqz(ma, ar)
sd = np.abs(h)**2/np.sqrt(2*np.pi)

if np.sum(np.isnan(h)) > 0:
    # this happens with unit root or seasonal unit root'
    print 'Warning: nan in frequency response h'
    h[np.isnan(h)] = 1.
    rescale = 0



#replace with signal.order_filter ?
pm = ndimage.filters.maximum_filter(sd, footprint=np.ones(5))
maxind = np.nonzero(pm == sd)
print 'local maxima frequencies'
wmax = w[maxind]
sdmax = sd[maxind]


plt.figure()
plt.subplot(2,3,1)
if rescale:
    plt.plot(w, sd/sd[0], '-', wmax, sdmax/sd[0], 'o')
#    plt.plot(w, sd/sd[0], '-')
#    plt.hold()
#    plt.plot(wmax, sdmax/sd[0], 'o')
else:
    plt.plot(w, sd, '-', wmax, sdmax, 'o')
#    plt.hold()
#    plt.plot(wmax, sdmax, 'o')

plt.title('DGP')

sdm, wm = mlb.psd(x)
sdm = sdm.ravel()
pm = ndimage.filters.maximum_filter(sdm, footprint=np.ones(5))
maxind = np.nonzero(pm == sdm)

plt.subplot(2,3,2)
if rescale:
    plt.plot(wm,sdm/sdm[0], '-', wm[maxind], sdm[maxind]/sdm[0], 'o')
else:
    plt.plot(wm, sdm, '-', wm[maxind], sdm[maxind], 'o')
plt.title('matplotlib')

if hastalkbox:
    sdp, wp = stbs.periodogram(x)
    plt.subplot(2,3,3)

    if rescale:
        plt.plot(wp,sdp/sdp[0])
    else:
        plt.plot(wp, sdp)
    plt.title('stbs.periodogram')

xacov = acovf(x, unbiased=False)
plt.subplot(2,3,4)
plt.plot(xacov)
plt.title('autocovariance')

nr = len(x)#*2/3
#xacovfft = np.fft.fft(xacov[:nr], 2*nr-1)
xacovfft = np.fft.fft(np.correlate(x,x,'full'))
#abs(xacovfft)**2 or equivalently
xacovfft = xacovfft * xacovfft.conj()

plt.subplot(2,3,5)
if rescale:
    plt.plot(xacovfft[:nr]/xacovfft[0])
else:
    plt.plot(xacovfft[:nr])

plt.title('fft')

if hastalkbox:
    sdpa, wpa = stbs.arspec(x, 50)
    plt.subplot(2,3,6)

    if rescale:
        plt.plot(wpa,sdpa/sdpa[0])
    else:
        plt.plot(wpa, sdpa)
    plt.title('stbs.arspec')


#plt.show()
