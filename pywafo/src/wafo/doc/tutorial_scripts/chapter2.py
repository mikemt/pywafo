import numpy as np
from scipy import *
from pylab import *

# pyreport -o chapter1.html chapter1.py

#! CHAPTER2 Modelling random loads and stochastic waves
#!=======================================================
#!
#! Chapter2 contains the commands used in Chapter 2 of the tutorial and
#! present some tools for analysis of random functions with
#! respect to their correlation, spectral and distributional properties.
#! The presentation is divided into three examples: 
#!
#! Example1 is devoted to estimation of different parameters in the model.
#! Example2 deals with spectral densities and
#! Example3 presents the use of WAFO to simulate samples of a Gaussian
#! process.
#!
#! Some of the commands are edited for fast computation. 
#! Each set of commands is followed by a 'pause' command.
#! 

#!
#! Tested on Matlab 5.3, 7.01
#! History
#! Revised by Georg Lindgren sept 2009 for WAFO ver 2.5 on Matlab 7.1
#! Revised pab sept2005
#! Added sections -> easier to evaluate using cellmode evaluation.
#! Revised pab Dec2004
#! Created by GL July 13, 2000
#! from commands used in Chapter 2
#!

pstate =  'off';

#! Section 2.1 Introduction and preliminary analysis
#!====================================================
#! Example 1: Sea data
#!----------------------
#! Observed crossings compared to the expected for Gaussian signals

import wafo
import wafo.objects as wo
xx = wafo.data.sea()
me = xx[:,1].mean()
sa = xx[:,1].std()
xx[:,1] -=  me
ts = wo.mat2timeseries(xx)
tp = ts.turning_points()


cc = tp.cycle_pairs()
lc = cc.level_crossings()
lc.plot()
show()

#! Average number of upcrossings per time unit
#!----------------------------------------------
#! Next we compute the mean frequency as the average number of upcrossings 
#! per time unit of the mean level (= 0); this may require interpolation in the 
#! crossing intensity curve, as follows.  
T = xx[:,0].max()-xx[:,0].min()
f0 = np.interp(0,lc.args,lc.data,0)/T  #! zero up-crossing frequency 

#! Turningpoints and irregularity factor
#!----------------------------------------

fm = len(tp.data)/(2*T)           #! frequency of maxima
alfa = f0/fm                     #! approx Tm24/Tm02
 
#! Visually examine data
#!------------------------
#! We finish this section with some remarks about the quality
#! of the measured data. Especially sea surface measurements can be
#! of poor quality. We shall now check the  quality of the dataset {\tt xx}. 
#! It is always good practice to visually examine the data 
#! before the analysis to get an impression of the quality, 
#! non-linearities and narrow-bandedness of the data.
#! First we shall plot the data and zoom in on a specific region. 
#! A part of sea data is visualized with the following commands
clf()
ts.plot_wave('k-',tp,'*',nfig=1, nsub=1)

axis([0, 2, -2, 2])
show()

#! Finding possible spurious points
#!------------------------------------
#! However, if the amount of data is too large for visual examinations one
#! could use the following criteria to find possible spurious points. One
#! must be careful using the criteria for extremevalue analysis, because
#! it might remove extreme waves that are OK and not spurious.

import wafo.misc as wm
dt = ts.sampling_period()
# dt = np.diff(xx[:2,0])
dcrit = 5*dt
ddcrit = 9.81/2*dt*dt
zcrit = 0
inds, indg = wm.findoutliers(xx[:,1],zcrit,dcrit,ddcrit, verbose=True)

#! Section 2.2 Frequency Modeling of Load Histories
#!----------------------------------------------------
#! Periodogram: Raw spectrum
#!
clf()
Lmax = 9500
S = ts.tospecdata(NFFT=Lmax)
S.plot()
axis([0, 5, 0, 0.7])
show()

#! Calculate moments  
#!-------------------
mom, text= S.moment(nr=4)
[sa, sqrt(mom[0])]

#! Section 2.2.1 Random functions in Spectral Domain - Gaussian processes
#!--------------------------------------------------------------------------
#! Smoothing of spectral estimate 
#1----------------------------------
#! By decreasing Lmax the spectrum estimate becomes smoother.

clf()
Lmax0 = 200; Lmax1 = 50
S1 = ts.tospecdata(NFFT=Lmax0)
S2 = ts.tospecdata(NFFT=Lmax1)
S1.plot('-.')
S2.plot()
show()

#! Estimated autocovariance
#!----------------------------
#! Obviously knowing the spectrum one can compute the covariance
#! function. The following matlab code will compute the covariance for the 
#! unimodal spectral density S1 and compare it with estimated 
#! covariance of the signal xx.
clf()
Lmax = 80
R1 = S1.tocovdata(nr=1)   
Rest = ts.tocovdata(lag=Lmax)
R1.plot('.')
Rest.plot()
show()

#! We can see in Figure below that the covariance function corresponding to 
#! the spectral density S2 significantly differs from the one estimated 
#! directly from data. 
#! It can be seen in Figure above that the covariance corresponding to S1 
#! agrees much better with the estimated covariance function

clf()
R2 = S2.tocovdata(nr=1)
R2.plot('.')
Rest.plot()
show()

#! Section 2.2.2 Transformed Gaussian models
#!-------------------------------------------
#! We begin with computing skewness and kurtosis
#! for the data set xx and compare it with the second order wave approximation
#! proposed by Winterstein:
import wafo.stats as ws
rho3 = ws.skew(xx[:,1])
rho4 = ws.kurtosis(xx[:,1])

sk, ku=S1.stats_nl(moments='sk' )
 
#! Comparisons of 3 transformations
clf()
import wafo.transform.models as wtm
gh = wtm.TrHermite(mean=me, sigma=sa, skew=sk, kurt=ku ).trdata()
g = wtm.TrLinear(mean=me, sigma=sa ).trdata()


#! Linear transformation
 
glc, gemp = lc.trdata()
g.plot('r')
glc.plot('b-') #! Transf. estimated from level-crossings
gh.plot('b-.')  #! Hermite Transf. estimated from moments
show()
 
#!  Test Gaussianity of a stochastic process.
#!---------------------------------------------
#! TESTGAUSSIAN simulates  e(g(u)-u) = int (g(u)-u)^2 du  for Gaussian processes 
#!  given the spectral density, S. The result is plotted if test0 is given.
#!  This is useful for testing if the process X(t) is Gaussian.
#!  If 95#! of TEST1 is less than TEST0 then X(t) is not Gaussian at a 5#! level.
#! 
#! As we see from the figure below: none of the simulated values of test1 is 
#! above 1.00. Thus the data significantly departs from a Gaussian distribution. 
clf()
test0 = glc.dist2gauss()
#! the following test takes time
N = len(xx)
test1 = S1.testgaussian(ns=N,cases=50,t0=test0)
sum(test1>test0)<5
show()

#! Normalplot of data xx
#!------------------------
#! indicates that the underlying distribution has a "heavy" upper tail and a
#! "light" lower tail. 
clf()
import pylab
ws.probplot(ts.data, dist='norm', plot=pylab)
show()
#! Section 2.2.3 Spectral densities of sea data
#!-----------------------------------------------
#! Example 2: Different forms of spectra
#!
import wafo.spectrum.models as wsm
clf()
Hm0 = 7; Tp = 11;
spec = wsm.Jonswap(Hm0=Hm0, Tp=Tp).tospecdata()
spec.plot()
show()

#! Directional spectrum and Encountered directional spectrum
#! Directional spectrum
clf()
D = wsm.Spreading('cos2s')
Sd = D.tospecdata2d(S)
Sd.plot()
show()


##!Encountered directional spectrum
##!--------------------------------- 
#clf()
#Se = spec2spec(Sd,'encdir',0,10);
#plotspec(Se), hold on
#plotspec(Sd,1,'--'), hold off
##!wafostamp('','(ER)')
#disp('Block = 17'),pause(pstate)
#
##!#! Frequency spectra
#clf
#Sd1 =spec2spec(Sd,'freq');
#Sd2 = spec2spec(Se,'enc');
#plotspec(spec), hold on
#plotspec(Sd1,1,'.'),
#plotspec(Sd2),
##!wafostamp('','(ER)')
#hold off
#disp('Block = 18'),pause(pstate)
#
##!#! Wave number spectrum
#clf
#Sk = spec2spec(spec,'k1d')
#Skd = spec2spec(Sd,'k1d')
#plotspec(Sk), hold on
#plotspec(Skd,1,'--'), hold off
##!wafostamp('','(ER)')
#disp('Block = 19'),pause(pstate)
#
##!#! Effect of waterdepth on spectrum
#clf
#plotspec(spec,1,'--'), hold on
#S20 = spec;
#S20.S = S20.S.*phi1(S20.w,20);
#S20.h = 20;
#plotspec(S20),  hold off
##!wafostamp('','(ER)')
#disp('Block = 20'),pause(pstate)
#
##!#! Section 2.3 Simulation of transformed Gaussian process
##!#! Example 3: Simulation of random sea    
##! The reconstruct function replaces the spurious points of seasurface by
##! simulated data on the basis of the remaining data and a transformed Gaussian
##! process. As noted previously one must be careful using the criteria 
##! for finding spurious points when reconstructing a dataset, because
##! these criteria might remove the highest and steepest waves as we can see
##! in this plot where the spurious points is indicated with a '+' sign:
##!
#clf
#[y, grec] = reconstruct(xx,inds);
#waveplot(y,'-',xx(inds,:),'+',1,1)
#axis([0 inf -inf inf])
##!wafostamp('','(ER)')
#disp('Block = 21'),pause(pstate)
#
##! Compare transformation (grec) from reconstructed (y) 
##! with original (glc) from (xx)
#clf
#trplot(g), hold on
#plot(gemp(:,1),gemp(:,2))
#plot(glc(:,1),glc(:,2),'-.')
#plot(grec(:,1),grec(:,2)), hold off 
#disp('Block = 22'),pause(pstate)
#
##!#!
#clf
#L = 200;
#x = dat2gaus(y,grec);
#Sx = dat2spec(x,L);
#disp('Block = 23'),pause(pstate)
#      
##!#!
#clf
#dt = spec2dt(Sx)
#Ny = fix(2*60/dt) #! = 2 minutes
#Sx.tr = grec;
#ysim = spec2sdat(Sx,Ny);
#waveplot(ysim,'-')
##!wafostamp('','(CR)')
#disp('Block = 24'),pause(pstate)
# 
##!#! Estimated spectrum compared to Torsethaugen spectrum
#clf
#Tp = 1.1;
#H0 = 4*sqrt(spec2mom(S1,1))
#St = torsethaugen([0:0.01:5],[H0  2*pi/Tp]);
#plotspec(S1)
#hold on
#plotspec(St,'-.')
#axis([0 6 0 0.4])
##!wafostamp('','(ER)')
#disp('Block = 25'),pause(pstate)
#
##!#!
#clf
#Snorm = St;
#Snorm.S = Snorm.S/sa^2;
#dt = spec2dt(Snorm)
#disp('Block = 26'),pause(pstate)
#
##!#!
#clf
#[Sk Su] = spec2skew(St);
#sa = sqrt(spec2mom(St,1));
#gh = hermitetr([],[sa sk ku me]);
#Snorm.tr = gh;
#disp('Block = 27'),pause(pstate)
#
##!#! Transformed Gaussian model compared to Gaussian model
#clf
#dt = 0.5;
#ysim_t = spec2sdat(Snorm,240,dt);
#xsim_t = dat2gaus(ysim_t,Snorm.tr);
#disp('Block = 28'),pause(pstate)
#
##!#! Compare
##! In order to compare the Gaussian and non-Gaussian models we need to scale  
##! \verb+xsim_t+ #!{\tt xsim$_t$} 
##! to have the same first spectral moment as 
##! \verb+ysim_t+,  #!{\tt ysim$_t$},  Since the process xsim_t has variance one
##! which will be done by the following commands. 
#clf
#xsim_t(:,2) = sa*xsim_t(:,2);
#waveplot(xsim_t,ysim_t,5,1,sa,4.5,'r.','b')
##!wafostamp('','(CR)')
#disp('Block = 29, Last block'),pause(pstate)

