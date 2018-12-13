# -*- coding: utf-8 -*-
"""
Who knows what this even is...

@authors: Giovani Ceotto, Matheus Marques Araujo, Rodrigo Schmitt
"""
import re
import math
import numpy as np
from scipy import integrate
from scipy import linalg
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from matplotlib import cm
import time
from datetime import datetime
from inspect import signature, getsourcelines
import bisect

try:
    import netCDF4
except ImportError:
    print('Unable to load netCDF4. NetCDF files will not be imported.')


class Function:
    """Class converts a python function or a data sequence into an object
    which can be handled more naturally, enabling easy interpolation,
    extrapolation, ploting and algebra.
    """
    def __init__(self,
                 source,
                 inputs=['Scalar'],
                 outputs=['Scalar'],
                 interpolation=None,
                 extrapolation=None):
        """ Convert source into a Function, to be used more naturally.
        Set inputs, outputs, domain dimension, interpolation and extrapolation
        method, and process the source.

        Parameters
        ----------
        source : function, scalar, ndarray, string
            The actual function. If type is function, it will be called for
            evaluation. If type is int or float, it will be treated as a
            constant function. If ndarray, its points will be used for
            interpolation. A ndarray should be as [(x0, y0, z0), (x1, y1, z1),
            (x2, y2, z2), ...] where x0 and y0 are inputs and z0 is output. If
            string, imports file named by the string and treats it as csv.
            The file is converted into ndarray and should not have headers.
        inputs : string, sequence of strings, optional
            The name of the inputs of the function. Will be used for
            representation and graphing (axis names). 'Scalar' is default.
            If source is function, int or float and has multiple inputs,
            this parameters must be giving for correct operation.
        outputs : string, sequence of strings, optional
            The name of the outputs of the function. Will be used for
            representation and graphing (axis names). Scalar is default.
        interpolation : string, optional
            Interpolation method to be used if source type is ndarray.
            For 1-D functions, linear, polynomail, akima and spline are
            supported. For N-D functions, only shepard is suporrted.
            Default for 1-D functions is spline.
        extrapolation : string, optional
            Extrapolation method to be used if source type is ndarray.
            Options are 'natural', which keeps interpolation, 'constant',
            which returns the value of the function of edge of the interval,
            and 'zero', which returns zero for all points outside of source
            range. Default for 1-D functions is constant.

        Returns
        -------
        None
        """
        # Set input and output
        self.setInputs(inputs)
        self.setOutputs(outputs)
        # Save interpolation method
        self.__interpolation__ = interpolation
        self.__extrapolation__ = extrapolation
        # Initialize last_interval
        self.last_interval = 0
        # Set source
        self.setSource(source)
        # Return
        return None

    # Define all set methods
    def setInputs(self, inputs):
        """Set the name and number of the incoming arguments of the Function.

        Parameters
        ----------
        inputs : string, sequence of strings
            The name of the parameters (inputs) of the Function.

        Returns
        -------
        self : Function
        """
        self.__inputs__ = [inputs] if isinstance(inputs, str) else list(inputs)
        self.__domDim__ = len(self.__inputs__)
        return self

    def setOutputs(self, outputs):
        """Set the name and number of the output of the Function.

        Parameters
        ----------
        outputs : string, sequence of strings
            The name of the output of the function. Example: Distance (m).

        Returns
        -------
        self : Function
        """
        self.__outputs__ = [outputs] if isinstance(outputs, str) else list(outputs)
        self.__imgDim__ = len(self.__outputs__)
        return self

    def setSource(self, source):
        """Set the source which defines the output of the function giving a
        certain input.

        Parameters
        ----------
        source : function, scalar, ndarray, string
            The actual function. If type is function, it will be called for
            evaluation. If type is int or float, it will be treated as a
            constant function. If ndarray, its points will be used for
            interpolation. A ndarray should be as [(x0, y0, z0), (x1, y1, z1),
            (x2, y2, z2), ...] where x0 and y0 are inputs and z0 is output. If
            string, imports file named by the string and treats it as csv.
            The file is converted into ndarray and should not have headers.

        Returns
        -------
        self : Function
        """
        # Import CSV if source is a string and convert values to ndarray
        if isinstance(source, str):
            # Read file and check for headers
            f = open(source, 'r')
            firstLine = f.readline()
            # If headers are found...
            if firstLine[0] in ['"', "'"]:
                # Headers available
                firstLine = firstLine.replace('"', ' ').replace("'", ' ')
                firstLine = firstLine.split(" , ")
                self.setInputs(firstLine[0])
                self.setOutputs(firstLine[1:])
                source = np.loadtxt(source, delimiter=',', skiprows=1, dtype=float)
            # if headers are not found
            else:
                source = np.loadtxt(source, delimiter=',', dtype=float)
        # Convert to ndarray if source is a list
        if isinstance(source, (list, tuple)):
            source = np.array(source, dtype=np.float64)
        # Convert number source into vectorized lambda function
        if isinstance(source, (int, float)):
            temp = 1*source
            source = lambda x: 0*x + temp
        # Handle callable source or number source
        if callable(source):
            # Set source
            self.source = source
            # Set geValueOpt2
            self.getValueOpt = source
            # Set arguments name and domain dimensions
            parameters = signature(source).parameters
            self.__domDim__ = len(parameters)
            if self.__inputs__ == ['Time (s)']:
                self.__inputs__ = list(parameters)
            # Set interpolation and extrapolation
            self.__interpolation__ = None
            self.__extrapolation__ = None
        # Handle ndarray source
        else:
            # Check to see if dimensions match incoming data set
            newTotalDim = len(source[0, :])
            oldTotalDim = self.__domDim__ + self.__imgDim__
            dV = (self.__inputs__ == ['Scalar'] and
                  self.__outputs__ == ['Scalar'])
            # If they dont, update default values or throw error
            if newTotalDim != oldTotalDim:
                if dV:
                    # Update dimensions and inputs
                    self.__domDim__ = newTotalDim - 1
                    self.__inputs__ = self.__domDim__*self.__inputs__
                else:
                    # User has made a mistake inputting inputs and outputs
                    print('Error in input and output dimensions!')
                    return None
            # Do things if domDim is 1
            if self.__domDim__ == 1:
                source = source[source[:, 0].argsort()]
                # Finally set data source as source
                self.source = source
                # Set default interpolation for point source if it hasn't
                if self.__interpolation__ is None:
                    self.setInterpolation()
                else:
                    # Updates interpolation coefficients
                    self.setInterpolation(self.__interpolation__)
            # Do things if function is multivariate
            else:
                # Finally set data source as source
                self.source = source
                if self.__interpolation__ is None:
                    self.setInterpolation('shepard')
            # Update extrapolation method
            if self.__extrapolation__ is None:
                self.setExtrapolation()
        # Return self
        return self

    def setInterpolation(self, method='spline'):
        """Set interpolation method and process data is method requires.

        Parameters
        ----------
        method : string, optional
            Interpolation method to be used if source type is ndarray.
            For 1-D functions, linear, polynomial, akima and spline is
            supported. For N-D functions, only shepard is suporrted.
            Default is 'spline'.

        Returns
        -------
        self : Function
        """
        # Set interpolation method
        self.__interpolation__ = method
        # Spline, akima and polynomial need data processing
        # Shepard, and linear do not
        if method == 'spline':
            self.__interpolateSpline__()
        elif method == 'polynomial':
            self.__interpolatePolynomial__()
        elif method == 'akima':
            self.__interpolateAkima__()
        
        # Set geValueOpt2
        self.setGetValueOpt()

        # Returns self
        return self

    def setExtrapolation(self, method='constant'):
        """Set extrapolation behavior of data set.

        Parameters
        ----------
        extrapolation : string, optional
            Extrapolation method to be used if source type is ndarray.
            Options are 'natural', which keeps interpolation, 'constant',
            which returns the value of the function of edge of the interval,
            and 'zero', which returns zero for all points outside of source
            range. Default is 'zero'.

        Returns
        -------
        self : Function
        """
        # Set extrapolation method
        self.__extrapolation__ = method
        # Return self
        return self

    def setGetValueOpt(self):
        """Crates a method that evaluates interpolations rather quickly
        when compared to other options available, such as just calling
        the object instance or calling self.getValue directly. See
        Function.getValueOpt for documentation.

        Returns
        -------
        self : Function
        """
        # Retrieve general info
        xData = self.source[:, 0]
        yData = self.source[:, 1]
        xmin, xmax = xData[0], xData[-1]
        if self.__extrapolation__ == 'zero':
            extrapolation = 0 # Extrapolation is zero
        elif self.__extrapolation__ == 'natural':
            extrapolation = 1 # Extrapolation is natural
        else:
            extrapolation = 2 # Extrapolation is constant

        # Crete method to interpolate this info for each interpolation type
        if self.__interpolation__ == 'spline':
            coeffs = self.__splineCoefficients__
            # @jit(nopython=True)
            def getValueOpt(x):
                xInterval = np.searchsorted(xData, x)
                # Interval found... interpolate... or extrapolate
                if xmin <= x <= xmax:
                    # Interpolate
                    xInterval = xInterval if xInterval != 0 else 1
                    a = coeffs[:, xInterval-1]
                    x = x - xData[xInterval-1]
                    y = (a[3]*x**3 + a[2]*x**2 + a[1]*x + a[0])
                else:
                    # Extrapolate
                    if extrapolation == 0: # Extrapolation == zero
                        y = 0 
                    elif extrapolation == 1: # Extrapolation == natural
                        a = coeffs[:, 0] if x < xmin else coeffs[:, -1]
                        x = x - xData[0] if x < xmin else x - xData[-2]
                        y = (a[3]*x**3 + a[2]*x**2 + a[1]*x + a[0])
                    else:  # Extrapolation is set to constant
                        y = yData[0] if x < xmin else yData[-1]
                return y
            self.getValueOpt = getValueOpt
        
        elif self.__interpolation__ == 'linear':
            # @jit(nopython=True)
            def getValueOpt(x):
                xInterval = np.searchsorted(xData, x)
                # Interval found... interpolate... or extrapolate
                if xmin <= x <= xmax:
                    # Interpolate
                    dx = float(xData[xInterval]-xData[xInterval-1])
                    dy = float(yData[xInterval]-yData[xInterval-1])
                    y = ((x-xData[xInterval-1])*(dy/dx) + yData[xInterval-1])
                else:
                    # Extrapolate
                    if extrapolation == 0: # Extrapolation == zero
                        y = 0 
                    elif extrapolation == 1: # Extrapolation == natural
                        xInterval = 1 if x < xmin else -1
                        dx = float(xData[xInterval]-xData[xInterval-1])
                        dy = float(yData[xInterval]-yData[xInterval-1])
                        y = ((x-xData[xInterval-1])*(dy/dx) + yData[xInterval-1])
                    else:  # Extrapolation is set to constant
                        y = yData[0] if x < xmin else yData[-1]
                return y
            self.getValueOpt = getValueOpt
        
        elif self.__interpolation__ == 'akima':
            coeffs = np.array(self.__akimaCoefficients__)
            # @jit(nopython=True)
            def getValueOpt(x):
                xInterval = np.searchsorted(xData, x)
                # Interval found... interpolate... or extrapolate
                if xmin <= x <= xmax:
                    # Interpolate
                    xInterval = xInterval if xInterval != 0 else 1
                    a = coeffs[4*xInterval - 4:4*xInterval]
                    y = (a[3]*x**3 + a[2]*x**2 + a[1]*x + a[0])
                else:
                    # Extrapolate
                    if extrapolation == 0: # Extrapolation == zero
                        y = 0 
                    elif extrapolation == 1: # Extrapolation == natural
                        a = coeffs[:4] if x < xmin else coeffs[-4:]
                        y = (a[3]*x**3 + a[2]*x**2 + a[1]*x + a[0])
                    else:  # Extrapolation is set to constant
                        y = yData[0] if x < xmin else yData[-1]
                return y
            self.getValueOpt = getValueOpt
        
        elif self.__interpolation__ == 'polynomial':
            coeffs = self.__polynomialCoefficients__
            # @jit(nopython=True)
            def getValueOpt(x):
                # Interpolate... or extrapolate
                if xmin <= x <= xmax:
                    # Interpolate
                    y = 0
                    for i in range(len(coeffs)):
                        y += coeffs[i]*(x**i)
                else:
                    # Extrapolate
                    if extrapolation == 0: # Extrapolation == zero
                        y = 0 
                    elif extrapolation == 1: # Extrapolation == natural
                        y = 0
                        for i in range(len(coeffs)):
                            y += coeffs[i]*(x**i)
                    else:  # Extrapolation is set to constant
                        y = yData[0] if x < xmin else yData[-1]
                return y
            self.getValueOpt = getValueOpt
        
        elif self.__interpolation__ == 'shepard':
            xData = self.source[:, 0:-1] # Support for N-Dimensions
            len_yData = len(yData) # A little speed up
            def getValueOpt(*args):
                x = np.array([[float(x) for x in list(args)]])
                numeratorSum = 0
                denominatorSum = 0
                for i in range(len_yData):
                    sub = xData[i] - x
                    distance = np.linalg.norm(sub)
                    if distance == 0:
                        numeratorSum = yData[i]
                        denominatorSum = 1
                        break
                    else:
                        weight = distance**(-3)
                        numeratorSum = numeratorSum + yData[i]*weight
                        denominatorSum = denominatorSum + weight
                return numeratorSum/denominatorSum
            self.getValueOpt = getValueOpt
        
        # Returns self
        return self

    def setDiscrete(self, lower=0, upper=10, samples=200,
                    interpolation='spline', extrapolation='constant',
                    oneByOne=True):
        """This method transforms function defined Functions into list
        defined Functions. It evaluates the function at certain points
        (sampling range) and stores the results in a list, which is converted
        into a Function and then returned. The original Function object is
        replaced by the new one.

        Parameters
        ----------
        lower : scalar, optional
            Value where sampling range will start. Default is 0.
        upper : scalar, optional
            Value where sampling range will end. Default is 10.
        samples : int, optional
            Number of samples to be taken from inside range. Default is 200.
        interpolation : string
            Interpolation method to be used if source type is ndarray.
            For 1-D functions, linear, polynomail, akima and spline is
            supported. For N-D functions, only shepard is suporrted.
            Default is 'spline'.
        extrapolation : string, optional
            Extrapolation method to be used if source type is ndarray.
            Options are 'natural', which keeps interpolation, 'constant',
            which returns the value of the function of edge of the interval,
            and 'zero', which returns zero for all points outside of source
            range. Default is 'constant'.
        oneByOne : boolean, optional
            If True, evaluate Function in each sample point separately. If
            False, evaluates Function in vectorized form. Default is True.

        Returns
        -------
        self : Function
        """
        if self.__domDim__ == 1:
            Xs = np.linspace(lower, upper, samples)
            Ys = self.getValue(Xs.tolist()) if oneByOne else self.getValue(Xs)
            self.source = np.concatenate(([Xs], [Ys])).transpose()
            self.setInterpolation(interpolation)
            self.setExtrapolation(extrapolation)
        elif self.__domDim__ == 2:
            lower = 2*[lower] if isinstance(lower, (int, float)) else lower
            upper = 2*[upper] if isinstance(upper, (int, float)) else upper
            sam = 2*[samples] if isinstance(samples, (int, float)) else samples
            # Create nodes to evaluate function
            Xs = np.linspace(lower[0], upper[0], sam[0])
            Ys = np.linspace(lower[1], upper[1], sam[1])
            Xs, Ys = np.meshgrid(Xs, Ys)
            Xs, Ys = Xs.flatten(), Ys.flatten()
            mesh = [[Xs[i], Ys[i]] for i in range(len(Xs))]
            # Evaluate function at all mesh nodes and convert it to matrix
            Zs = np.array(self.getValue(mesh))
            self.source = np.concatenate(([Xs], [Ys], [Zs])).transpose()
            self.__interpolation__ = 'shepard'
        return self

    # Define all get methods
    def getInputs(self):
        'Return tuple of inputs of the function.'
        return self.__inputs__

    def getOutputs(self):
        'Return tuple of outputs of the function.'
        return self.__outputs__

    def getSource(self):
        'Return source list or function of the function.'
        return self.source

    def getImageDim(self):
        'Return int describing dimension of the image space of the function.'
        return self.__imgDim__

    def getDomainDim(self):
        'Return int describing dimension of the domain space of the function.'
        return self.__domDim__

    def getInterpolationMethod(self):
        'Return string describing interpolation method used.'
        return self.__interpolation__

    def getExtrapolationMethod(self):
        'Return string describing extrapolation method used.'
        return self.__extrapolation__

    def getValue(self, *args):
        """This method returns the value of the Function at the specified
        point. See Function.getValueOpt for a faster, but limited,
        implementation.

        Parameters
        ----------
        args : scalar, list
            Value where the Function is to be evaluated. If the Function is
            1-D, only one argument is expected, which may be an int, a float
            or a list of ints or floats, in which case the Function will be
            evaluated at all points in the list and a list of floats will be
            returned. If the function is N-D, N arguments must be given, each
            one being an scalar or list.

        Returns
        -------
        ans : scalar, list
        """
        # Return value for Function of function type
        if callable(self.source):
            if len(args) == 1 and isinstance(args[0], (list, tuple)):
                if isinstance(args[0][0], (tuple, list)):
                    return [self.source(*arg) for arg in args[0]]
                else:
                    return [self.source(arg) for arg in args[0]]
            elif len(args) == 1 and isinstance(args[0], np.ndarray):
                return self.source(args[0])
            else:
                return self.source(*args)
        # Returns value for shepard interpolation
        elif self.__interpolation__ == 'shepard':
            if isinstance(args[0], (list, tuple)):
                x = list(args[0])
            else:
                x = [[float(x) for x in list(args)]]
            ans = x
            xData = self.source[:, 0:-1]
            yData = self.source[:, -1]
            for i in range(len(x)):
                numeratorSum = 0
                denominatorSum = 0
                for o in range(len(yData)):
                    sub = xData[o] - x[i]
                    distance = (sub.dot(sub))**(0.5)
                    # print(xData[o], x[i], distance)
                    if distance == 0:
                        numeratorSum = yData[o]
                        denominatorSum = 1
                        break
                    else:
                        weight = distance**(-3)
                        numeratorSum = numeratorSum + yData[o]*weight
                        denominatorSum = denominatorSum + weight
                ans[i] = numeratorSum/denominatorSum
            return ans if len(ans) > 1 else ans[0]
        # Returns value for polynomial interpolation function type
        elif self.__interpolation__ == 'polynomial':
            if isinstance(args[0], (int, float)):
                args = [list(args)]
            x = np.array(args[0])
            xData = self.source[:, 0]
            yData = self.source[:, 1]
            xmin, xmax = xData[0], xData[-1]
            coeffs = self.__polynomialCoefficients__
            A = np.zeros((len(args[0]), coeffs.shape[0]))
            for i in range(coeffs.shape[0]):
                A[:, i] = x**i
            ans = A.dot(coeffs).tolist()
            for i in range(len(x)):
                if not (xmin <= x[i] <= xmax):
                    if self.__extrapolation__ == 'constant':
                        ans[i] = yData[0] if x[i] < xmin else yData[-1]
                    elif self.__extrapolation__ == 'zero':
                        ans[i] = 0
            return ans if len(ans) > 1 else ans[0]
        # Returns value for spline, akima or linear interpolation function type
        elif self.__interpolation__ in ['spline', 'akima', 'linear']:
            if isinstance(args[0], (int, float, complex)):
                args = [list(args)]
            x = [arg for arg in args[0]]
            xData = self.source[:, 0]
            yData = self.source[:, 1]
            xIntervals = np.searchsorted(xData, x)
            xmin, xmax = xData[0], xData[-1]
            if self.__interpolation__ == 'spline':
                coeffs = self.__splineCoefficients__
                for i in range(len(x)):
                    if x[i] == xmin or x[i] == xmax:
                        x[i] = yData[xIntervals[i]]
                    elif xmin < x[i] < xmax or (self.__extrapolation__ ==
                                                'natural'):
                        if not xmin < x[i] < xmax:
                            a = coeffs[:, 0] if x[i] < xmin else coeffs[:, -1]
                            x[i] = x[i] - xData[0] if x[i] < xmin else x[i] - xData[-2]
                        else:
                            a = coeffs[:, xIntervals[i]-1]
                            x[i] = x[i] - xData[xIntervals[i]-1]
                        x[i] = (a[3]*x[i]**3 + a[2]*x[i]**2 + a[1]*x[i] + a[0])
                    else:
                        # Extrapolate
                        if self.__extrapolation__ == 'zero':
                            x[i] = 0
                        else:  # Extrapolation is set to constant
                            x[i] = yData[0] if x[i] < xmin else yData[-1]
            elif self.__interpolation__ == 'linear':
                for i in range(len(x)):
                    # Interval found... interpolate... or extrapolate
                    inter = xIntervals[i]
                    if xmin <= x[i] <= xmax:
                        # Interpolate
                        dx = float(xData[inter]-xData[inter-1])
                        dy = float(yData[inter]-yData[inter-1])
                        x[i] = ((x[i]-xData[inter-1])*(dy/dx) + yData[inter-1])
                    else:
                        # Extrapolate
                        if self.__extrapolation__ == 'zero': # Extrapolation == zero
                            x[i] = 0 
                        elif self.__extrapolation__ == 'natural': # Extrapolation == natural
                            inter = 1 if x[i] < xmin else -1
                            dx = float(xData[inter]-xData[inter-1])
                            dy = float(yData[inter]-yData[inter-1])
                            x[i] = ((x[i]-xData[inter-1])*(dy/dx) + yData[inter-1])
                        else:  # Extrapolation is set to constant
                            x[i] = yData[0] if x[i] < xmin else yData[-1]
            else:
                coeffs = self.__akimaCoefficients__
                for i in range(len(x)):
                    if x[i] == xmin or x[i] == xmax:
                        x[i] = yData[xIntervals[i]]
                    elif xmin < x[i] < xmax or (self.__extrapolation__ ==
                                                'natural'):
                        if not (xmin < x[i] < xmax):
                            a = coeffs[:4] if x[i] < xmin else coeffs[-4:]
                        else:
                            a = coeffs[4*xIntervals[i]-4:4*xIntervals[i]]
                        x[i] = (a[3]*x[i]**3 + a[2]*x[i]**2 +
                                a[1]*x[i] + a[0])
                    else:
                        # Extrapolate
                        if self.__extrapolation__ == 'zero':
                            x[i] = 0
                        else:  # Extrapolation is set to constant
                            x[i] = yData[0] if x[i] < xmin else yData[-1]
            if isinstance(args[0], np.ndarray):
                return np.array(x)
            else:
                return x if len(x) > 1 else x[0]

    def getValueOpt(self, *args):
        """This method returns the value of the Function at the specified
        point in a limited but optimized manner. See Function.getValue for an
        implementation which allows more kinds of inputs.
        This method optimizes the Function.getValue method by only
        implementing function evaluations of single inputs, i.e., it is not
        vectorized. Furthermore, it actually implements a different method
        for each interpolation type, eliminating some if statements.
        Currently supports callables and spline, linear, akima, polynomial and
        shepard interpolated Function objects.
        The code below is here for documentation proposes only. It is
        overwritten for all instances by the Function.setGetValuteOpt method.

        Parameters
        ----------
        args : scalar
            Value where the Function is to be evaluated. If the Function is
            1-D, only one argument is expected, which may be an int or a float
            If the function is N-D, N arguments must be given, each one being
            an int or a float.

        Returns
        -------
        x : scalar
        """
        # Callables
        if callable(self.source):
            return self.source(*args)

        # Interpolated Function
        # Retrieve general info
        xData = self.source[:, 0]
        yData = self.source[:, 1]
        xmin, xmax = xData[0], xData[-1]
        if self.__extrapolation__ == 'zero':
            extrapolation = 0 # Extrapolation is zero
        elif self.__extrapolation__ == 'natural':
            extrapolation = 1 # Extrapolation is natural
        else:
            extrapolation = 2 # Extrapolation is constant

        # Interpolate this info for each interpolation type
        # Spline
        if self.__interpolation__ == 'spline':
            x = args[0]
            coeffs = self.__splineCoefficients__
            xInterval = np.searchsorted(xData, x)
            # Interval found... interpolate... or extrapolate
            if xmin <= x <= xmax:
                # Interpolate
                xInterval = xInterval if xInterval != 0 else 1
                a = coeffs[:, xInterval-1]
                x = x - xData[xInterval-1]
                y = (a[3]*x**3 + a[2]*x**2 + a[1]*x + a[0])
            else:
                # Extrapolate
                if extrapolation == 0: # Extrapolation == zero
                    y = 0 
                elif extrapolation == 1: # Extrapolation == natural
                    a = coeffs[:, 0] if x < xmin else coeffs[:, -1]
                    x = x - xData[0] if x < xmin else x - xData[-2]
                    y = (a[3]*x**3 + a[2]*x**2 + a[1]*x + a[0])
                else:  # Extrapolation is set to constant
                    y = yData[0] if x < xmin else yData[-1]
            return y
        # Linear
        elif self.__interpolation__ == 'linear':
            x = args[0]
            xInterval = np.searchsorted(xData, x)
            # Interval found... interpolate... or extrapolate
            if xmin <= x <= xmax:
                # Interpolate
                dx = float(xData[xInterval]-xData[xInterval-1])
                dy = float(yData[xInterval]-yData[xInterval-1])
                y = ((x-xData[xInterval-1])*(dy/dx) + yData[xInterval-1])
            else:
                # Extrapolate
                if extrapolation == 0: # Extrapolation == zero
                    y = 0 
                elif extrapolation == 1: # Extrapolation == natural
                    xInterval = 1 if x < xmin else -1
                    dx = float(xData[xInterval]-xData[xInterval-1])
                    dy = float(yData[xInterval]-yData[xInterval-1])
                    y = ((x-xData[xInterval-1])*(dy/dx) + yData[xInterval-1])
                else:  # Extrapolation is set to constant
                    y = yData[0] if x < xmin else yData[-1]
            return y
        # Akima
        elif self.__interpolation__ == 'akima':
            x = args[0]
            coeffs = np.array(self.__akimaCoefficients__)
            xInterval = np.searchsorted(xData, x)
            # Interval found... interpolate... or extrapolate
            if xmin <= x <= xmax:
                # Interpolate
                xInterval = xInterval if xInterval != 0 else 1
                a = coeffs[4*xInterval - 4:4*xInterval]
                y = (a[3]*x**3 + a[2]*x**2 + a[1]*x + a[0])
            else:
                # Extrapolate
                if extrapolation == 0: # Extrapolation == zero
                    y = 0 
                elif extrapolation == 1: # Extrapolation == natural
                    a = coeffs[:4] if x < xmin else coeffs[-4:]
                    y = (a[3]*x**3 + a[2]*x**2 + a[1]*x + a[0])
                else:  # Extrapolation is set to constant
                    y = yData[0] if x < xmin else yData[-1]
            return y
        # Polynominal
        elif self.__interpolation__ == 'polynomial':
            x = args[0]
            coeffs = self.__polynomialCoefficients__
            # Interpolate... or extrapolate
            if xmin <= x <= xmax:
                # Interpolate
                y = 0
                for i in range(len(coeffs)):
                    y += coeffs[i]*(x**i)
            else:
                # Extrapolate
                if extrapolation == 0: # Extrapolation == zero
                    y = 0 
                elif extrapolation == 1: # Extrapolation == natural
                    y = 0
                    for i in range(len(coeffs)):
                        y += coeffs[i]*(x**i)
                else:  # Extrapolation is set to constant
                    y = yData[0] if x < xmin else yData[-1]
            return y
        # Shepard
        elif self.__interpolation__ == 'shepard':
            xData = self.source[:, 0:-1] # Support for N-Dimensions
            len_yData = len(yData) # A little speed up
            x = np.array([[float(x) for x in list(args)]])
            numeratorSum = 0
            denominatorSum = 0
            for i in range(len_yData):
                sub = xData[i] - x
                distance = np.linalg.norm(sub)
                if distance == 0:
                    numeratorSum = yData[i]
                    denominatorSum = 1
                    break
                else:
                    weight = distance**(-3)
                    numeratorSum = numeratorSum + yData[i]*weight
                    denominatorSum = denominatorSum + weight
            return numeratorSum/denominatorSum

    def getValueOpt2(self, *args):
        """DEPRECATED!! - See Function.getValueOpt for new version.
        This method returns the value of the Function at the specified
        point in a limited but optimized manner. See Function.getValue for an
        implementation which allows more kinds of inputs.
        This method optimizes the Function.getValue method by only
        implementing function evaluations of single inputes, i.e., it is not
        vectorized. Furthermore, it actually implements a different method
        for each interpolation type, eliminating some if statements.
        Finally, it uses Numba to compile the methods, which further optmizes
        the implementation.
        The code below is here for documentation porpuses only. It is
        overwritten for all instances by the Function.setGetValuteOpt2 method.

        Parameters
        ----------
        args : scalar
            Value where the Function is to be evaluated. If the Function is
            1-D, only one argument is expected, which may be an int or a float
            If the function is N-D, N arguments must be given, each one being
            an int or a float.

        Returns
        -------
        x : scalar
        """
        # Returns value for function function type
        if callable(self.source):
            return self.source(*args)
        # Returns value for spline, akima or linear interpolation function type
        elif self.__interpolation__ in ['spline', 'akima', 'linear']:
            x = args[0]
            xData = self.source[:, 0]
            yData = self.source[:, 1]
            # Hunt in intervals near the last interval which was used.
            xInterval = self.last_interval 
            if xData[xInterval - 1] <= x <= xData[xInterval]:
                pass
            else:
                xInterval = np.searchsorted(xData, x)
                self.last_interval = xInterval if xInterval < len(xData) else 0
            # Interval found... keep going
            xmin, xmax = xData[0], xData[-1]
            if self.__interpolation__ == 'spline':
                coeffs = self.__splineCoefficients__
                if x == xmin or x == xmax:
                    x = yData[xInterval]
                elif xmin < x < xmax or (self.__extrapolation__ == 'natural'):
                    if not xmin < x < xmax:
                        a = coeffs[:, 0] if x < xmin else coeffs[:, -1]
                        x = x - xData[0] if x < xmin else x - xData[-2]
                    else:
                        a = coeffs[:, xInterval-1]
                        x = x - xData[xInterval-1]
                    x = (a[3]*x**3 + a[2]*x**2 + a[1]*x + a[0])
                else:
                    # Extrapolate
                    if self.__extrapolation__ == 'zero':
                        x = 0
                    else:  # Extrapolation is set to constant
                        x = yData[0] if x < xmin else yData[-1]
            elif self.__interpolation__ == 'linear':
                if x == xmin or x == xmax:
                    x = yData[xInterval]
                elif xmin < x < xmax or (self.__extrapolation__ == 'natural'):
                    dx = float(xData[xInterval]-xData[xInterval-1])
                    dy = float(yData[xInterval]-yData[xInterval-1])
                    x = ((x-xData[xInterval-1])*(dy/dx) + yData[xInterval - 1])
                elif self.__extrapolation__ == 'natural':
                    y0 = yData[0] if x < xmin else yData[-1]
                    xInterval = 1 if x < xmin else -1
                    dx = float(xData[xInterval]-xData[xInterval-1])
                    dy = float(yData[xInterval]-yData[xInterval-1])
                    x = ((x-xData[xInterval-1])*(dy/dx) + y0)
                else:
                    # Extrapolate
                    if self.__extrapolation__ == 'zero':
                        x = 0
                    else:  # Extrapolation is set to constant
                        x = yData[0] if x < xmin else yData[-1]
            else:
                if self.__interpolation__ == 'akima':
                    coeffs = self.__akimaCoefficients__
                if x == xmin or x == xmax:
                    x = yData[xInterval]
                elif xmin < x < xmax:
                    a = coeffs[4*xInterval - 4:4*xInterval]
                    x = (a[3]*x**3 + a[2]*x**2 + a[1]*x + a[0])
                elif self.__extrapolation__ == 'natural':
                    a = coeffs[:4] if x < xmin else coeffs[-4:]
                    x = (a[3]*x**3 + a[2]*x**2 + a[1]*x + a[0])
                else:
                    # Extrapolate
                    if self.__extrapolation__ == 'zero':
                        x = 0
                    else:  # Extrapolation is set to constant
                        x = yData[0] if x < xmin else yData[-1]
            return x

    def __getitem__(self, args):
        '''Returns item of the Function source. If the source is not an array,
        an error will result.
        
        Parameters
        ----------
        args : int, float
            Index of the item to be retrieved.
        
        Returns
        -------
        self.source[args] : float, array
            Item specified from Function.source.
        '''
        return self.source[args]

    def __len__(self):
        '''Returns length of the Function source. If the source is not an
        array, an error will result.
            
        Returns
        -------
        len(self.source) : int
            Length of Function.source.
        '''
        return len(self.source)

    # Define all presentation methods
    def __call__(self, *args):
        """Plot the Function if no argument is given. If an
        argument is given, return the value of the function at the desired
        point.

        Parameters
        ----------
        args : scalar, list, optional
            Value where the Function is to be evaluated. If the Function is
            1-D, only one argument is expected, which may be an int, a float
            or a list of ints or floats, in which case the Function will be
            evaluated at all points in the list and a list of floats will be
            returned. If the function is N-D, N arguments must be given, each
            one being an scalar or list.

        Returns
        -------
        ans : None, scalar, list
        """
        if len(args) == 0:
            return self.plot()
        else:
            return self.getValue(*args)

    def __str__(self):
        "Return a string representation of the Function"
        return ('Function from R' + str(self.__domDim__) + ' to R' +
                str(self.__imgDim__) +
                ' : (' +
                ', '.join(self.__inputs__) + ') → (' +
                ', '.join(self.__outputs__)+')')

    def __repr__(self):
        "Return a string representation of the Function"
        return ('Function from R' + str(self.__domDim__) + ' to R' +
                str(self.__imgDim__) +
                ' : (' +
                ', '.join(self.__inputs__) + ') → (' +
                ', '.join(self.__outputs__)+')')

    def plot(self, *args, **kwargs):
        """Call Function.plot1D if Function is 1-Dimensional or call
        Function.plot2D if Function is 2-Dimensional and forward arguments
        and key-word arguments."""
        if isinstance(self, list):
            # Compare multiple plots
            Function.comparePlots(self)
        else:
            if self.__domDim__ == 1:
                self.plot1D(*args, **kwargs)
            elif self.__domDim__ == 2:
                self.plot2D(*args, **kwargs)
            else:
                print('Error: Only functions with 1D or 2D domains are plottable!')

    def plot1D(self, lower=None, upper=None, samples=1000, forceData=False,
               forcePoints=False, returnObject=False):
        """ Plot 1-Dimensional Function, from a lower limit to an upper limit,
        by sampling the Function several times in the interval. The title of
        the graph is given by the name of the axis, which are taken from
        the Function`s input and ouput names.

        Parameters
        ----------
        lower : scalar, optional
            The lower limit of the interval in which the function is to be
            ploted. The default value for function type Functions is 0. By
            contrast, if the Function is given by a dataset, the default
            value is the start of the dataset.
        upper : scalar, optional
            The upper limit of the interval in which the function is to be
            ploted. The default value for function type Functions is 10. By
            contrast, if the Function is given by a dataset, the default
            value is the end of the dataset.
        samples : int, optional
            The number of samples in which the function will be evaluated for
            plotting it, which draws lines between each evaluated point.
            The default value is 1000.
        forceData : Boolean, optional
            If Function is given by an interpolated dataset, setting forceData
            to True will plot all points, as a scatter, in the dataset.
            Default value is False.
        forcePoints : Boolean, optional
            Setting forcePoints to True will plot all points, as a scatter, in
            which the Function was evaluated in the dataset. Default value is
            False.

        Returns
        -------
        None
        """
        # Define a mesh and y values at mesh nodes for plotting
        fig = plt.figure()
        ax = fig._get_axes
        if callable(self.source):
            # Determine boundaries
            lower = 0 if lower is None else lower
            upper = 10 if upper is None else upper
        else:
            # Determine boundaries
            xData = self.source[:, 0]
            xmin, xmax = xData[0], xData[-1]
            lower = xmin if lower is None else lower
            upper = xmax if upper is None else upper
            # Plot data points if forceData = True
            tooLow = True if xmin >= lower else False
            tooHigh = True if xmax <= upper else False
            loInd = 0 if tooLow else np.where(xData >= lower)[0][0]
            upInd = len(xData) - 1 if tooHigh else np.where(xData <= upper)[0][0]
            points = self.source[loInd:(upInd+1), :].T.tolist()
            if forceData:
                plt.scatter(points[0], points[1], marker='o')
        # Calculate function at mesh nodes
        x = np.linspace(lower, upper, samples)
        y = self.getValue(x.tolist())
        # Plots function
        if forcePoints:
            plt.scatter(x, y, marker='o')
        plt.plot(x, y)
        # Turn on grid and set title and axis
        plt.grid(True)
        plt.title(self.__outputs__[0].title() + ' x ' +
                  self.__inputs__[0].title())
        plt.xlabel(self.__inputs__[0].title())
        plt.ylabel(self.__outputs__[0].title())
        plt.show()
        if returnObject:
            return fig, ax

    def plot2D(self, lower=None, upper=None, samples=[30, 30], forceData=True,
               dispType='surface'):
        """ Plot 2-Dimensional Function, from a lower limit to an upper limit,
        by sampling the Function several times in the interval. The title of
        the graph is given by the name of the axis, which are taken from
        the Function`s inputs and ouput names.

        Parameters
        ----------
        lower : scalar, array of int or float, optional
            The lower limits of the interval in which the function is to be
            ploted, which can be an int or float, which is repeated for both
            axis, or an array specifying the limit for each axis. The default
            value for function type Functions is 0. By contrast, if the
            Function is given by a dataset, the default value is the start of
            the dataset for each axis.
        upper : scalar, array of int or float, optional
            The upper limits of the interval in which the function is to be
            ploted, which can be an int or float, which is repeated for both
            axis, or an array specifying the limit for each axis. The default
            value for function type Functions is 0. By contrast, if the
            Function is given by a dataset, the default value is the end of
            the dataset for each axis.
        samples : int, array of int, optional
            The number of samples in which the function will be evaluated for
            plotting it, which draws lines between each evaluated point.
            The default value is 30 for each axis.
        forceData : Boolean, optional
            If Function is given by an interpolated dataset, setting forceData
            to True will plot all points, as a scatter, in the dataset.
            Default value is False.
        dispType : string, optional
            Display type of plotted graph, which can be surface, wireframe,
            contour, or contourf. Default value is surface.

        Returns
        -------
        None
        """
        # Prepare plot
        figure = plt.figure()
        axes = figure.gca(projection='3d')
        # Define a mesh and f values at mesh nodes for plotting
        if callable(self.source):
            # Determine boundaries
            lower = [0, 0] if lower is None else lower
            lower = 2*[lower] if isinstance(lower, (int, float)) else lower
            upper = [10, 10] if upper is None else upper
            upper = 2*[upper] if isinstance(upper, (int, float)) else upper
        else:
            # Determine boundaries
            xData = self.source[:, 0]
            yData = self.source[:, 1]
            xMin, xMax = xData.min(), xData.max()
            yMin, yMax = yData.min(), yData.max()
            lower = [xMin, yMin] if lower is None else lower
            lower = 2*[lower] if isinstance(lower, (int, float)) else lower
            upper = [xMax, yMax] if upper is None else upper
            upper = 2*[upper] if isinstance(upper, (int, float)) else upper
            # Plot data points if forceData = True
            if forceData:
                axes.scatter(xData, yData, self.source[:, -1])
        # Create nodes to evaluate function
        x = np.linspace(lower[0], upper[0], samples[0])
        y = np.linspace(lower[1], upper[1], samples[1])
        meshX, meshY = np.meshgrid(x, y)
        meshXFlat, meshYFlat = meshX.flatten(), meshY.flatten()
        mesh = [[meshXFlat[i], meshYFlat[i]] for i in range(len(meshXFlat))]
        # Evaluate function at all mesh nodes and convert it to matrix
        z = np.array(self.getValue(mesh)).reshape(meshX.shape)
        # Plot function
        if dispType == 'surface':
            surf = axes.plot_surface(meshX, meshY, z, rstride=1, cstride=1,
                                     cmap=cm.coolwarm, linewidth=0, alpha=0.6)
            figure.colorbar(surf)
        elif dispType == 'wireframe':
            axes.plot_wireframe(meshX, meshY, z, rstride=1, cstride=1)
        elif dispType == 'contour':
            figure.clf()
            CS = plt.contour(meshX, meshY, z)
            plt.clabel(CS, inline=1, fontsize=10)
        elif dispType == 'contourf':
            figure.clf()
            CS = plt.contour(meshX, meshY, z)
            plt.contourf(meshX, meshY, z)
            plt.clabel(CS, inline=1, fontsize=10)
        # axes.contourf(meshX, meshY, z, zdir='x', offset=xMin, cmap=cm.coolwarm)
        # axes.contourf(meshX, meshY, z, zdir='y', offset=yMax, cmap=cm.coolwarm)
        plt.title(self.__outputs__[0].title() + ' x ' +
                  self.__inputs__[0].title() + ' x ' +
                  self.__inputs__[1].title())
        axes.set_xlabel(self.__inputs__[0].title())
        axes.set_ylabel(self.__inputs__[1].title())
        axes.set_zlabel(self.__outputs__[0].title())
        plt.show()

    def comparePlots(self, lower=None, upper=None, samples=1000,
                     title="", xlabel="", ylabel="",
                     forceData=False, forcePoints=False, returnObject=False):
        """ Plots N 1-Dimensional Functions in the same plot, from a lower
        limit to an upper limit, by sampling the Function several times in
        the interval.

        Parameters
        ----------
        self : list
            List of Functions or list of tuples in the format (Function,
            label), where label is a string which will be displayed in the
            legend.
        lower : scalar, optional
            The lower limit of the interval in which the Functions are to be
            ploted. The default value for function type Functions is 0. By
            contrast, if the Functions given are defined by a dataset, the
            default value is the lowest value of the datasets.
        upper : scalar, optional
            The upper limit of the interval in which the Functions are to be
            ploted. The default value for function type Functions is 10. By
            contrast, if the Functions given are defined by a dataset, the
            default value is the highest value of the datasets.
        samples : int, optional
            The number of samples in which the functions will be evaluated for
            plotting it, which draws lines between each evaluated point.
            The default value is 1000.
        title : string, optional
            Title of the plot. Default value is an empty string.
        xlabel : string, optional
            X-axis label. Default value is an empty string.
        ylabel : string, optional
            Y-axis label. Default value is an empty string.
        forceData : Boolean, optional
            If Function is given by an interpolated dataset, setting forceData
            to True will plot all points, as a scatter, in the dataset.
            Default value is False.
        forcePoints : Boolean, optional
            Setting forcePoints to True will plot all points, as a scatter, in
            which the Function was evaluated to plot it. Default value is
            False.

        Returns
        -------
        None
        """
        noRangeSpecified = True if lower is None and upper is None else False
        # Convert to list of tuples if list of Function was given
        plots = []
        if isinstance(self[0], (tuple, list)) == False:
            for i in range(len(plots)):
                plots.append((plot, " "))
        else:
            plots = self

        # Create plot figure
        fig, ax = plt.subplots()

        # Define a mesh and y values at mesh nodes for plotting
        if lower is None:
            lower = 0
            for plot in plots:
                if not callable(plot[0].source):
                    # Determine boundaries
                    xmin = plot[0].source[0, 0]
                    lower = xmin if xmin < lower else lower
        if upper is None:
            upper = 10
            for plot in plots:
                if not callable(plot[0].source):
                    # Determine boundaries
                    xmax = plot[0].source[-1, 0]
                    upper = xmax if xmax > upper else upper
        x = np.linspace(lower, upper, samples)

        # Iterate to plot all plots
        for plot in plots:
            # Deal with discrete data sets when no range is given
            if noRangeSpecified and not callable(plot[0].source):
                ax.plot(plot[0][:, 0], plot[0][:, 1], label=plot[1])
                if forcePoints:
                    ax.scatter(plot[0][:, 0], plot[0][:, 1], marker='o')
            else:
                # Calculate function at mesh nodes
                y = plot[0].getValue(x.tolist())
                # Plots function
                ax.plot(x, y, label=plot[1])
                if forcePoints:
                    ax.scatter(x, y, marker='o')
    
        # Plot data points if specified
        if forceData:
            for plot in plots:
                if not callable(plot[0].source):
                    xData = plot[0].source[:, 0]
                    xmin, xmax = xData[0], xData[-1]
                    tooLow = True if xmin >= lower else False
                    tooHigh = True if xmax <= upper else False
                    loInd = 0 if tooLow else np.where(xData >= lower)[0][0]
                    upInd = len(xData) - 1 if tooHigh else np.where(xData <= upper)[0][0]
                    points = plot[0].source[loInd:(upInd+1), :].T.tolist()
                    ax.scatter(points[0], points[1], marker='o')

        # Setup legend
        ax.legend(loc='best', shadow=True)

        # Turn on grid and set title and axis
        plt.grid(True)
        plt.title(title)
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)

        # Show plot
        plt.show()

        if returnObject:
            return fig, ax

    # Define all interpolation methods
    def __interpolatePolynomial__(self):
        """"Calculate polynomail coefficients that fit the data exactly."""
        # Find the degree of the polynomial interpolation
        degree = self.source.shape[0] - 1
        # Get x and y values for all supplied points.
        x = self.source[:, 0]
        y = self.source[:, 1]
        # Check if interpolation requires large numbers
        if np.amax(x)**degree > 1e308:
            print("Polynomial interpolation of too many points can't be done."
                  " Once the degree is too high, numbers get too large."
                  " The process becomes inefficient. Using spline instead.")
            return self.setInterpolation('spline')
        # Create coefficient matrix1
        A = np.zeros((degree + 1, degree + 1))
        for i in range(degree + 1):
            A[:, i] = x**i
        # Solve the system and store the resultant coefficients
        self.__polynomialCoefficients__ = np.linalg.solve(A, y)

    def __interpolateSpline__(self):
        """Calculate natural spline coefficients that fit the data exactly."""
        # Get x and y values for all supplied points
        x = self.source[:, 0]
        y = self.source[:, 1]
        mdim = len(x)
        h = [x[i+1] - x[i] for i in range(0, mdim - 1)]
        # Initialize the matrix
        Ab = np.zeros((3, mdim))
        # Construct the Ab banded matrix and B vector
        Ab[1, 0] = 1  # A[0, 0] = 1
        B = [0]
        for i in range(1, mdim-1):
            Ab[2, i - 1] = h[i - 1]  # A[i, i - 1] = h[i - 1]
            Ab[1, i] = 2*(h[i] + h[i - 1])  # A[i, i] = 2*(h[i] + h[i - 1])
            Ab[0, i + 1] = h[i]  # A[i, i + 1] = h[i]
            B.append(3*((y[i + 1] - y[i])/(h[i]) - (y[i] - y[i - 1])/(h[i-1])))
        Ab[1, mdim - 1] = 1  # A[-1, -1] = 1
        B.append(0)
        # Solve the system for c coefficients
        c = linalg.solve_banded((1, 1), Ab, B, True, True)
        # Calculate other coefficients
        b = [((y[i+1] - y[i])/h[i] - h[i]*(2*c[i]+c[i+1])/3)
             for i in range(0, mdim-1)]
        d = [(c[i+1] - c[i])/(3*h[i]) for i in range(0, mdim - 1)]
        # Store coefficients
        self.__splineCoefficients__ = np.array([y[0:-1], b, c[0:-1], d])

    def __interpolateAkima__(self):
        """Calculate akima spline coefficients that fit the data exactly"""
        # Get x and y values for all supplied points
        x = self.source[:, 0]
        y = self.source[:, 1]
        # Estimate derivatives at each point
        d = [0]*len(x)
        d[0] = (y[1] - y[0])/(x[1] - x[0])
        d[-1] = (y[-1] - y[-2])/(x[-1] - x[-2])
        for i in range(1, len(x) - 1):
            w1, w2 = (x[i] - x[i-1]), (x[i+1] - x[i])
            d1, d2 = ((y[i] - y[i-1])/w1), ((y[i+1] - y[i])/w2)
            d[i] = (w1*d2+w2*d1)/(w1+w2)
        # Calculate coefficients for each interval with system already solved
        coeffs = [0]*4*(len(x)-1)
        for i in range(len(x)-1):
            xl, xr = x[i], x[i+1]
            yl, yr = y[i], y[i+1]
            dl, dr = d[i], d[i+1]
            A = np.array([[1, xl, xl**2, xl**3],
                          [1, xr, xr**2, xr**3],
                          [0, 1, 2*xl, 3*xl**2],
                          [0, 1, 2*xr, 3*xr**2]])
            Y = np.array([yl, yr, dl, dr]).T
            coeffs[4*i:4*i+4] = np.linalg.solve(A, Y)
            """For some reason this doesn't always work!
            coeffs[4*i] = (dr*xl**2*xr*(-xl + xr) + dl*xl*xr**2*(-xl + xr) +
                           3*xl*xr**2*yl - xr**3*yl + xl**3*yr -
                          3*xl**2*xr*yr)/(xl-xr)**3
            coeffs[4*i+1] = (dr*xl*(xl**2 + xl*xr - 2*xr**2) -
                             xr*(dl*(-2*xl**2 + xl*xr + xr**2) +
                             6*xl*(yl - yr)))/(xl-xr)**3
            coeffs[4*i+2] = (-dl*(xl**2 + xl*xr - 2*xr**2) +
                             dr*(-2*xl**2 + xl*xr + xr**2) +
                             3*(xl + xr)*(yl - yr))/(xl-xr)**3
            coeffs[4*i+3] = (dl*(xl - xr) + dr*(xl - xr) -
                             2*yl + 2*yr)/(xl-xr)**3"""
        self.__akimaCoefficients__ = coeffs

    # Define all possible algebraic operations
    def __truediv__(self, other):
        """Devides a Function object and returns a new Function object
        which gives the result of the division. Only implemented for 1D
        domains.

        Parameters
        ----------
        other : Function, int, float, callable
            What self will be divided by. If other and self are Function
            objects which are based on interpolation, have the exact same
            domain (are defined in the same grid points), have the same
            interpolation method and have the same input name, then a
            special implementation is used. This implementation is faster,
            however behavior between grid points is only interpolated,
            not calculated as it would be.

        Returns
        -------
        result : Function
            A Function object which gives the result of self(x)/other(x).
        """
        # If other is Function try...
        try:
            # Check if Function objects source is array or callable
            # Check if Function objects have same interpolation and domain
            if (isinstance(other.source, np.ndarray) and
                isinstance(self.source, np.ndarray) and
                self.__interpolation__ == other.__interpolation__ and
                self.__inputs__ == other.__inputs__ and
                np.any(self.source[:, 0] - other.source[:, 0]) == False):
                # Operate on grid values
                Ys = self.source[:, 1]/other.source[:, 1]
                Xs = self.source[:, 0]
                source = np.concatenate(([Xs], [Ys])).transpose()
                # Retrieve inputs, outputs and interpolation
                inputs = self.__inputs__[:]
                outputs = self.__outputs__[0] + '/' + other.__outputs__[0]
                outputs = '(' + outputs + ')'
                interpolation = self.__interpolation__
                # Create new Function object
                return Function(source, inputs, outputs, interpolation)
            else:
                return Function(lambda x: (self.getValueOpt2(x)/other(x)))
        # If other is Float except...
        except:
            if isinstance(other, (float, int, complex)):
                # Check if Function object source is array or callable
                if isinstance(self.source, np.ndarray):
                    # Operate on grid values
                    Ys = self.source[:, 1]/other
                    Xs = self.source[:, 0]
                    source = np.concatenate(([Xs], [Ys])).transpose()
                    # Retrieve inputs, outputs and interpolation
                    inputs = self.__inputs__[:]
                    outputs = self.__outputs__[0] + '/' + str(other)
                    outputs = '(' + outputs + ')'
                    interpolation = self.__interpolation__
                    # Create new Function object
                    return Function(source, inputs, outputs, interpolation)
                else:
                    return Function(lambda x: (self.getValueOpt2(x)/other))
            # Or if it is just a callable
            elif callable(other):
                return Function(lambda x: (self.getValueOpt2(x)/other(x)))

    def __rtruediv__(self, other):
        """Devides 'other' by a Function object and returns a new Function
        object which gives the result of the division. Only implemented for
        1D domains.

        Parameters
        ----------
        other : int, float, callable
            What self will divide.

        Returns
        -------
        result : Function
            A Function object which gives the result of other(x)/self(x).
        """
        # Check if Function object source is array and other is float
        if isinstance(other, (float, int, complex)):
            if isinstance(self.source, np.ndarray):
                # Operate on grid values
                Ys = other/self.source[:, 1]
                Xs = self.source[:, 0]
                source = np.concatenate(([Xs], [Ys])).transpose()
                # Retrieve inputs, outputs and interpolation
                inputs = self.__inputs__[:]
                outputs = str(other) + '/' + self.__outputs__[0]
                outputs = '(' + outputs + ')'
                interpolation = self.__interpolation__
                # Create new Function object
                return Function(source, inputs, outputs, interpolation)
            else:
                return Function(lambda x: (other/self.getValueOpt2(x)))
        # Or if it is just a callable
        elif callable(other):
            return Function(lambda x: (other(x)/self.getValueOpt2(x)))

    def __pow__(self, other):
        """Raises a Function object to the power of 'other' and
        returns a new Function object which gives the result. Only
        implemented for 1D domains.

        Parameters
        ----------
        other : Function, int, float, callable
            What self will be raised to. If other and self are Function
            objects which are based on interpolation, have the exact same
            domain (are defined in the same grid points), have the same
            interpolation method and have the same input name, then a
            special implementation is used. This implementation is faster,
            however behavior between grid points is only interpolated,
            not calculated as it would be.

        Returns
        -------
        result : Function
            A Function object which gives the result of self(x)**other(x).
        """
        # If other is Function try...
        try:
            # Check if Function objects source is array or callable
            # Check if Function objects have same interpolation and domain
            if (isinstance(other.source, np.ndarray) and
                isinstance(self.source, np.ndarray) and
                self.__interpolation__ == other.__interpolation__ and
                self.__inputs__ == other.__inputs__ and
                np.any(self.source[:, 0] - other.source[:, 0]) == False):
                # Operate on grid values
                Ys = self.source[:, 1]**other.source[:, 1]
                Xs = self.source[:, 0]
                source = np.concatenate(([Xs], [Ys])).transpose()
                # Retrieve inputs, outputs and interpolation
                inputs = self.__inputs__[:]
                outputs = self.__outputs__[0] + '**' + other.__outputs__[0]
                outputs = '(' + outputs + ')'
                interpolation = self.__interpolation__
                # Create new Function object
                return Function(source, inputs, outputs, interpolation)
            else:
                return Function(lambda x: (self.getValueOpt2(x)**other(x)))
        # If other is Float except...
        except:
            if isinstance(other, (float, int, complex)):
                # Check if Function object source is array or callable
                if isinstance(self.source, np.ndarray):
                    # Operate on grid values
                    Ys = self.source[:, 1]**other
                    Xs = self.source[:, 0]
                    source = np.concatenate(([Xs], [Ys])).transpose()
                    # Retrieve inputs, outputs and interpolation
                    inputs = self.__inputs__[:]
                    outputs = self.__outputs__[0] + '**' + str(other)
                    outputs = '(' + outputs + ')'
                    interpolation = self.__interpolation__
                    # Create new Function object
                    return Function(source, inputs, outputs, interpolation)
                else:
                    return Function(lambda x: (self.getValue(x)**other))
            # Or if it is just a callable
            elif callable(other):
                return Function(lambda x: (self.getValue(x)**other(x)))

    def __rpow__(self, other):
        """Raises 'other' to the power of a Function object and returns
        a new Function object which gives the result. Only implemented
        for 1D domains.

        Parameters
        ----------
        other : int, float, callable
            What self will exponantiate.

        Returns
        -------
        result : Function
            A Function object which gives the result of other(x)**self(x).
        """
        # Check if Function object source is array and other is float
        if isinstance(other, (float, int, complex)):
            if isinstance(self.source, np.ndarray):
                # Operate on grid values
                Ys = other**self.source[:, 1]
                Xs = self.source[:, 0]
                source = np.concatenate(([Xs], [Ys])).transpose()
                # Retrieve inputs, outputs and interpolation
                inputs = self.__inputs__[:]
                outputs = str(other) + '**' + self.__outputs__[0]
                outputs = '(' + outputs + ')'
                interpolation = self.__interpolation__
                # Create new Function object
                return Function(source, inputs, outputs, interpolation)
            else:
                return Function(lambda x: (other**self.getValue(x)))
        # Or if it is just a callable
        elif callable(other):
            return Function(lambda x: (other(x)**self.getValue(x)))

    def __mul__(self, other):
        """Multiplies a Function object and returns a new Function object
        which gives the result of the multiplication. Only implemented for 1D
        domains.

        Parameters
        ----------
        other : Function, int, float, callable
            What self will be multiplied by. If other and self are Function
            objects which are based on interpolation, have the exact same
            domain (are defined in the same grid points), have the same
            interpolation method and have the same input name, then a
            special implementation is used. This implementation is faster,
            however behavior between grid points is only interpolated,
            not calculated as it would be.

        Returns
        -------
        result : Function
            A Function object which gives the result of self(x)*other(x).
        """
        # If other is Function try...
        try:
            # Check if Function objects source is array or callable
            # Check if Function objects have same interpolation and domain
            if (isinstance(other.source, np.ndarray) and
                isinstance(self.source, np.ndarray) and
                self.__interpolation__ == other.__interpolation__ and
                self.__inputs__ == other.__inputs__ and
                np.any(self.source[:, 0] - other.source[:, 0]) == False):
                # Operate on grid values
                Ys = self.source[:, 1]*other.source[:, 1]
                Xs = self.source[:, 0]
                source = np.concatenate(([Xs], [Ys])).transpose()
                # Retrieve inputs, outputs and interpolation
                inputs = self.__inputs__[:]
                outputs = self.__outputs__[0] + '*' + other.__outputs__[0]
                outputs = '(' + outputs + ')'
                interpolation = self.__interpolation__
                # Create new Function object
                return Function(source, inputs, outputs, interpolation)
            else:
                return Function(lambda x: (self.getValue(x)*other(x)))
        # If other is Float except...
        except:
            if isinstance(other, (float, int, complex)):
                # Check if Function object source is array or callable
                if isinstance(self.source, np.ndarray):
                    # Operate on grid values
                    Ys = self.source[:, 1]*other
                    Xs = self.source[:, 0]
                    source = np.concatenate(([Xs], [Ys])).transpose()
                    # Retrieve inputs, outputs and interpolation
                    inputs = self.__inputs__[:]
                    outputs = self.__outputs__[0] + '*' + str(other)
                    outputs = '(' + outputs + ')'
                    interpolation = self.__interpolation__
                    # Create new Function object
                    return Function(source, inputs, outputs, interpolation)
                else:
                    return Function(lambda x: (self.getValue(x)*other))
            # Or if it is just a callable
            elif callable(other):
                return Function(lambda x: (self.getValue(x)*other(x)))

    def __rmul__(self, other):
        """Multiplies 'other' by a Function object and returns a new Function
        object which gives the result of the multiplication. Only implemented for
        1D domains.

        Parameters
        ----------
        other : int, float, callable
            What self will be multiplied by.

        Returns
        -------
        result : Function
            A Function object which gives the result of other(x)*self(x).
        """
        # Check if Function object source is array and other is float
        if isinstance(other, (float, int, complex)):
            if isinstance(self.source, np.ndarray):
                # Operate on grid values
                Ys = other*self.source[:, 1]
                Xs = self.source[:, 0]
                source = np.concatenate(([Xs], [Ys])).transpose()
                # Retrieve inputs, outputs and interpolation
                inputs = self.__inputs__[:]
                outputs = str(other) + '*' + self.__outputs__[0]
                outputs = '(' + outputs + ')'
                interpolation = self.__interpolation__
                # Create new Function object
                return Function(source, inputs, outputs, interpolation)
            else:
                return Function(lambda x: (other*self.getValue(x)))
        # Or if it is just a callable
        elif callable(other):
            return Function(lambda x: (other(x)*self.getValue(x)))

    def __add__(self, other):
        """Sums a Function object and 'other', returns a new Function
        object which gives the result of the sum. Only implemented for
        1D domains.

        Parameters
        ----------
        other : Function, int, float, callable
            What self will be added to. If other and self are Function
            objects which are based on interpolation, have the exact same
            domain (are defined in the same grid points), have the same
            interpolation method and have the same input name, then a
            special implementation is used. This implementation is faster,
            however behavior between grid points is only interpolated,
            not calculated as it would be.

        Returns
        -------
        result : Function
            A Function object which gives the result of self(x)+other(x).
        """
        # If other is Function try...
        try:
            # Check if Function objects source is array or callable
            # Check if Function objects have same interpolation and domain
            if (isinstance(other.source, np.ndarray) and
                isinstance(self.source, np.ndarray) and
                self.__interpolation__ == other.__interpolation__ and
                self.__inputs__ == other.__inputs__ and
                np.any(self.source[:, 0] - other.source[:, 0]) == False):
                # Operate on grid values
                Ys = self.source[:, 1] + other.source[:, 1]
                Xs = self.source[:, 0]
                source = np.concatenate(([Xs], [Ys])).transpose()
                # Retrieve inputs, outputs and interpolation
                inputs = self.__inputs__[:]
                outputs = self.__outputs__[0] + ' + ' + other.__outputs__[0]
                outputs = '(' + outputs + ')'
                interpolation = self.__interpolation__
                # Create new Function object
                return Function(source, inputs, outputs, interpolation)
            else:
                return Function(lambda x: (self.getValue(x) + other(x)))
        # If other is Float except...
        except:
            if isinstance(other, (float, int, complex)):
                # Check if Function object source is array or callable
                if isinstance(self.source, np.ndarray):
                    # Operate on grid values
                    Ys = self.source[:, 1] + other
                    Xs = self.source[:, 0]
                    source = np.concatenate(([Xs], [Ys])).transpose()
                    # Retrieve inputs, outputs and interpolation
                    inputs = self.__inputs__[:]
                    outputs = self.__outputs__[0] + ' + ' + str(other)
                    outputs = '(' + outputs + ')'
                    interpolation = self.__interpolation__
                    # Create new Function object
                    return Function(source, inputs, outputs, interpolation)
                else:
                    return Function(lambda x: (self.getValue(x) + other))
            # Or if it is just a callable
            elif callable(other):
                return Function(lambda x: (self.getValue(x) + other(x)))

    def __radd__(self, other):
        """Sums 'other' and a Function object and returns a new Function
        object which gives the result of the sum. Only implemented for
        1D domains.

        Parameters
        ----------
        other : int, float, callable
            What self will be added to.

        Returns
        -------
        result : Function
            A Function object which gives the result of other(x)/+self(x).
        """
        # Check if Function object source is array and other is float
        if isinstance(other, (float, int, complex)):
            if isinstance(self.source, np.ndarray):
                # Operate on grid values
                Ys = other + self.source[:, 1]
                Xs = self.source[:, 0]
                source = np.concatenate(([Xs], [Ys])).transpose()
                # Retrieve inputs, outputs and interpolation
                inputs = self.__inputs__[:]
                outputs = str(other) + ' + ' + self.__outputs__[0]
                outputs = '(' + outputs + ')'
                interpolation = self.__interpolation__
                # Create new Function object
                return Function(source, inputs, outputs, interpolation)
            else:
                return Function(lambda x: (other + self.getValue(x)))
        # Or if it is just a callable
        elif callable(other):
            return Function(lambda x: (other(x) + self.getValue(x)))

    def __sub__(self, other):
        """Subtracts from a Function object and returns a new Function object
        which gives the result of the subtraction. Only implemented for 1D
        domains.

        Parameters
        ----------
        other : Function, int, float, callable
            What self will be subtracted by. If other and self are Function
            objects which are based on interpolation, have the exact same
            domain (are defined in the same grid points), have the same
            interpolation method and have the same input name, then a
            special implementation is used. This implementation is faster,
            however behavior between grid points is only interpolated,
            not calculated as it would be.

        Returns
        -------
        result : Function
            A Function object which gives the result of self(x)-other(x).
        """
        # If other is Function try...
        try:
            # Check if Function objects source is array or callable
            # Check if Function objects have same interpolation and domain
            if (isinstance(other.source, np.ndarray) and
                isinstance(self.source, np.ndarray) and
                self.__interpolation__ == other.__interpolation__ and
                self.__inputs__ == other.__inputs__ and
                np.any(self.source[:, 0] - other.source[:, 0]) == False):
                # Operate on grid values
                Ys = self.source[:, 1] - other.source[:, 1]
                Xs = self.source[:, 0]
                source = np.concatenate(([Xs], [Ys])).transpose()
                # Retrieve inputs, outputs and interpolation
                inputs = self.__inputs__[:]
                outputs = self.__outputs__[0] + ' - ' + other.__outputs__[0]
                outputs = '(' + outputs + ')'
                interpolation = self.__interpolation__
                # Create new Function object
                return Function(source, inputs, outputs, interpolation)
            else:
                return Function(lambda x: (self.getValue(x)*other(x)))
        # If other is Float except...
        except:
            if isinstance(other, (float, int, complex)):
                # Check if Function object source is array or callable
                if isinstance(self.source, np.ndarray):
                    # Operate on grid values
                    Ys = self.source[:, 1] - other
                    Xs = self.source[:, 0]
                    source = np.concatenate(([Xs], [Ys])).transpose()
                    # Retrieve inputs, outputs and interpolation
                    inputs = self.__inputs__[:]
                    outputs = self.__outputs__[0] + ' - ' + str(other)
                    outputs = '(' + outputs + ')'
                    interpolation = self.__interpolation__
                    # Create new Function object
                    return Function(source, inputs, outputs, interpolation)
                else:
                    return Function(lambda x: (self.getValue(x) - other))
            # Or if it is just a callable
            elif callable(other):
                return Function(lambda x: (self.getValue(x) - other(x)))

    def __rsub__(self, other):
        """Subtracts a Function object from 'other' and returns a new Function
        object which gives the result of the subtraction. Only implemented for
        1D domains.

        Parameters
        ----------
        other : int, float, callable
            What self will subtract from.

        Returns
        -------
        result : Function
            A Function object which gives the result of other(x)-self(x).
        """
        # Check if Function object source is array and other is float
        if isinstance(other, (float, int, complex)):
            if isinstance(self.source, np.ndarray):
                # Operate on grid values
                Ys = other - self.source[:, 1]
                Xs = self.source[:, 0]
                source = np.concatenate(([Xs], [Ys])).transpose()
                # Retrieve inputs, outputs and interpolation
                inputs = self.__inputs__[:]
                outputs = str(other) + ' - ' + self.__outputs__[0]
                outputs = '(' + outputs + ')'
                interpolation = self.__interpolation__
                # Create new Function object
                return Function(source, inputs, outputs, interpolation)
            else:
                return Function(lambda x: (other - self.getValue(x)))
        # Or if it is just a callable
        elif callable(other):
            return Function(lambda x: (other(x) - self.getValue(x)))

    def integral(self, a, b, numerical=False):
        """ Evaluate a definite integral of a 1-D Function in the interval
        from a to b.

        Parameters
        ----------
        a : float
            Lower limit of integration.
        b : float
            Upper limit of integration.
        numerical : bool
            If True, forces the definite integral to be evaluated numerically.
            The current numerical method used is scipy.integrate.quad.
            If False, try to calculate using interpolation information.
            Currently, only available for spline and linear interpolation. If
            unavailable, calculate numerically anyways.
        
        Returns
        -------
        ans : float
            Evaluated integral.
        """
        if self.__interpolation__ == 'spline' and numerical is False:
            # Integrate using spline coefficients
            xData = self.source[:, 0]
            yData = self.source[:, 1]
            coeffs = self.__splineCoefficients__
            ans = 0
            # Check to see if interval starts before point data
            if a < xData[0]:
                if self.__extrapolation__ == 'constant':
                    ans += yData[0] * (xData[0] - a)
                elif self.__extrapolation__ == 'natural':
                    c = coeffs[:, 0]
                    subB = a - xData[0] # subA = 0
                    ans -= ((c[3]*subB**4)/4 +
                            (c[2]*subB**3/3) +
                            (c[1]*subB**2/2) +
                            c[0]*subB)
                else:
                    # self.__extrapolation__ = 'zero'
                    pass
            # Integrate in subintervals between Xs of given data up to b
            i = 0
            while i < len(xData) - 1 and xData[i] < b:
                if b < xData[i+1]:
                    subB = b - xData[i] # subA = 0
                else:
                    subB = xData[i+1] - xData[i] # subA = 0
                c = coeffs[:, i]
                subB = xData[i+1] - xData[i] # subA = 0
                ans += ((c[3]*subB**4)/4 +
                        (c[2]*subB**3/3) +
                        (c[1]*subB**2/2) +
                        c[0]*subB)
                i += 1
            # Check to see if interval ends after point data
            if b > xData[-1]:
                if self.__extrapolation__ == 'constant':
                    ans += yData[-1] * (b - xData[-1])
                elif self.__extrapolation__ == 'natural':
                    c = coeffs[:, -1]
                    subA = xData[-1] - xData[-2]
                    subB = b - xData[-2]
                    ans -= ((c[3]*subA**4)/4 +
                            (c[2]*subA**3/3) +
                            (c[1]*subA**2/2) +
                            c[0]*subA)
                    ans += ((c[3]*subB**4)/4 +
                            (c[2]*subB**3/3) +
                            (c[1]*subB**2/2) +
                            c[0]*subB)
                else:
                    # self.__extrapolation__ = 'zero'
                    pass
        elif self.__interpolation__ == 'linear' and numerical is False:
            return np.trapz(self.source[:,1], x=self.source[:,0])
        else:
            # Integrate numerically
            ans, error = integrate.quad(self, a, b, epsabs=0.1, limit=10000)
        return ans

    # Not implemented
    def differentiate(self, x, dx=1e-6):
        return (self.getValue(x+dx) - self.getValue(x-dx))/(2*dx)
        # h = (10)**-300
        # z = x + h*1j
        # return self(z).imag/h


class Environment:
    """Keeps all environment information stored, such as wind and temperature
    conditions, as well as gravity and rail length.
    
    Class attributes
    ----------------
    
        Gravity and Rail Length:
        Environment.rl : float
            Launch rail length in meters.
        Environment.g : float
            Positive value of gravitational acceleration in m/s^2.

        Atmosphere Static Conditions:
        Environment.densitySL : float
            Sea level air density in kg/m^3. Default value is 1.225.
            Defined by US Standard Atmosphere.
        Environment.pressureSL : float
            Sea level atmospheric pressure in Pa. Default value is 
            1.0132 * 10**5. Defined by US Standard Atmosphere.
        Environment.temperatureSL : float
            Sea level air temperature in Kelvin. Default value is 288.15.
            Defined by US Standard Atmosphere.
        Environment.speedOfSoundSL : float
            Sea level speed of sound in air in m/s. Default value is 340.3.
            Defined by US Standard Atmosphere.
        Environment.viscositySL : float
            Sea level air viscosity in kg/m*s. Default value is 1.79*10**(-5).
            Defined by US Standard Atmosphere.
        Environment.pressure : Function
            Air pressure in Pa as a function of altitude. Defined by US
            Standard Atmosphere.
        Environment.temperature : Function
            Air temperature in K as a function of altitude. Defined by US
            Standard Atmosphere.
        Environment.speedOfSound : Function
            Speed of sound in air as a function of altitude. Defined by US
            Standard Atmosphere.
        
        Atmosphere Wind Conditions: 
        Environment.windDataSource : string
            Indicates how the wind data was imported. Can be 'CSV',
            'netCDF', 'pair' and 'matrix'.
        Environment.windSpeed : Function
            Wind speed in m/s as a function of altitude.
        Environment.windHeading : Function
            Wind heading in degrees relative to north (positive clockwise)
            as a function of altitude.
        Environment.windVelocityX : Function
            X (east) component of wind velocity in m/s as a function of
            altitude.
        Environment.windVelocityY : Function
            Y (east) component of wind velocity in m/s as a function of
            altitude.
        Environment.maxExpectedHeight : float
            Maximum altitude in meters to keep weather data.
        Environment.lonIndex : int
            Defined if netCDF file is used. Index of the desired longitude
            in the file.
        Environment.latIndex : int
            Defined if netCDF file is used. Index of the desired latitude
            in the file. 
        Environment.geopotentials : list
            Defined if netCDF file is used. List of geopotentials available
            in the latitude and longitude specified.
        Environment.windUs : list
            Defined if netCDF file is used. List of wind velocity U (east)
            component corresponding to geopotential list.
        Environment.windVs : list
            Defined if netCDF file is used. List of wind velocity V (north)
            component corresponding to geopotential list.
        Environment.levels : list
            Defined if netCDF file is used. List of pressure levels
            corresponding to geopotential list.
        Environment.times : list
            Defined if netCDF file is used.
        Environment.height : list
            Defined if netCDF file is used.
        
        Spacetime position:
        Environment.lat : float
            Launch position latitude.
        Environment.lon : float
            Launch position longitude.
        Environment.date : datetime
            Date time of launch.    
    """
    def __init__(self,
                 railLength,
                 gravity=9.8,
                 windData=(0, 0),
                 location=None,
                 date=None):
        """Initialize Environment class, process rail, gravity and
        atmospheric data and store the results.

        Parameters
        ----------
        railLength : scalar
            Length in which the rocket will be attached to the rail, only
            moving along a fixed direction, that is, the line parallel to the
            rail.
        gravity : scalar, optional
            Surface gravitational acceleration. Positive values point the
            acceleration down. Default value is 9.8.
        windData : array of scalars or functions, string, optional
            Wind and atmospheric data input. If array of two scalars or
            functions is given, the first value is interpreted as wind speed, 
            while the second value is interpreted as an angle, in degrees,
            specifying direction relative to north (0 deg). The scalar values
            will be interpreted as constants, while function values can
            are interpreted as a function of altitude in meters.If matrix
            (Nx3) is given, the first column must be height data, the second
            wind speed data, and the third must be wind direction data. If
            string is given, it must point to a CSV or a netCDF file, which
            will be  imported. In the case of the CSV file, it must have no
            headers, the first column must contain height values, the second
            column must contain wind speed data, in m/s, and the third column
            must contain wind direction data, in deg. In the case of the
            netCDF file, it should contain wind velocity data and geopotential
            data, both for several pressure levels. Default value is (0, 0),
            corresponding to no wind.
        location : array of float, optional
            Array of length 2, stating (latitude, longitude) of rocket launch
            location. Must be given if wind data source is a netCDF file,
            other wise it is optional.
        date : array, optional
            Array of length 4, stating (year, month, day, hour (UTC)) of
            rocket launch. Must be given if wind data source is a netCDF file,
            other wise it is optional.

        Returns
        -------
        None
        """
        # Define Rail Length
        self.rL = railLength

        # Define gravity
        self.g = gravity

        # Define US Standard Atmosphere.
        self.densitySL = 1.225 # kg/m3
        self.pressureSL = 1.0132 * 10**5 # Pa
        self.temperatureSL = 288.15 # K
        self.speedOfSoundSL = 340.3 # m/s
        self.viscositySL = 1.79 * 10**(-5) # kg/m-s
        self.pressure = Function(lambda z: ((1.0132 * 10**5)*np.exp(-0.118*(z/1000)
                                            - (0.0015*(z/1000)**2)/(1-0.018*(z/1000) + 
                                            0.0011*(z/1000)**2))),
                                 'Altitude (m)', 'Pressure (Pa)')
        self.temperature = Function(lambda z: (216.65 + 2*np.log(1 + np.exp(35.75 - 3.25*(z/1000)) +
                                               np.exp(-3 + 0.0003*(z/1000)**3))),
                                    'Altitude (m)', 'Temperature (K)')
        self.speedOfSound = Function(lambda z: (401.856*(216.65 + 2*np.log(1 + np.exp(35.75 - 3.25*(z/1000)) +
                                                       np.exp(-3 + 0.0003*(z/1000)**3))))**0.5,
                                     'Altitude (m)', 'Speed of Sound (m/s)')
        self.density = Function(lambda z:((1.0132 * 10**5)*np.exp(-0.118*(z/1000) -
                                          (0.0015*(z/1000)**2)/(1-0.018*(z/1000) +
                                          0.0011*(z/1000)**2))) /
                                         (287.04*(216.65 + 2*np.log(1 + np.exp(35.75 - 3.25*(z/1000)) +
                                         np.exp(-3 + 0.0003*(z/1000)**3)))),
                                'Altitude (m)', 'Density (kg/m3)')

        # Define Spacetime Location
        if location is None:
            self.lat, self.lon = None, None
        else:
            self.lat, self.lon = location
        if date is None:
            self.date = None
        else:
            self.date = datetime(*date)

        # Import wind data
        self.maxExpectedHeight = 1000
        # Process string input
        if isinstance(windData, str):
            # Store CSV input
            if windData[-4:] == '.csv':
                self.windDataSource = 'CSV'
                windData = np.loadtxt(windData, delimiter=',')
                h, ws, wd = windData[:, 0], windData[:, 1], windData[:, 2]
                wx, wy = ws * np.sin(wd*np.pi/180), ws * np.cos(wd*np.pi/180)
                self.windSpeed = Function(np.column_stack((h, ws)), 'Height (m)', 'Wind Speed (m/s)')
                self.windHeading = Function(np.column_stack((h, wd)), 'Height (m)', 'Wind Heading (deg)')
                self.windVelocityX = Function(np.column_stack((h, wx)), 'Height (m)', 'Wind Velocity X (m/s)')
                self.windVelocityY = Function(np.column_stack((h, wy)), 'Height (m)', 'Wind Velocity y (m/s)')
                self.maxExpectedHeight = windData[-1, 0]
            # Store netCDF input
            elif windData[-3:] == '.nc':
                self.windDataSource = 'netCDF'
                windData = netCDF4.Dataset(windData)
                self.processNetCDFFile(windData)
            # Throw error if string input not recognized
            else:
                raise TypeError('Only .csv and .nc file formats '
                                'are supported.')
        # Process array input
        elif isinstance(windData, (tuple, list, np.ndarray)):
            # Process pair array input
            if len(windData) == 2:
                self.windDataSource = 'pair'
                ws, wd = windData[0], windData[1]
                if callable(ws) and callable(wd):
                    wx = Function(lambda h: ws(h) * np.sin(wd(h)*np.pi/180))
                    wy = Function(lambda h: ws(h) * np.cos(wd(h)*np.pi/180))
                elif callable(ws):
                    wx = Function(lambda h: ws(h) * np.sin(wd*np.pi/180))
                    wy = Function(lambda h: ws(h) * np.cos(wd*np.pi/180))
                elif callable(wd):
                    wx = Function(lambda h: ws * np.sin(wd(h)*np.pi/180))
                    wy = Function(lambda h: ws * np.cos(wd(h)*np.pi/180))
                else:
                    wx = ws * np.sin(wd*np.pi/180)
                    wy = ws * np.cos(wd*np.pi/180)
                self.windSpeed = Function(ws, 'Height (m)', 'Wind Speed (m/s)')
                self.windHeading = Function(wd, 'Height (m)', 'Wind Heading (deg)')
                self.windVelocityX = Function(wx, 'Height (m)', 'Wind Velocity X (m/s)')
                self.windVelocityY = Function(wy, 'Height (m)', 'Wind Velocity Y (m/s)')
            # Process dataset matrix input
            elif np.array(windData).shape[1] == 3:
                self.windDataSource = 'matrix'
                windData = np.array(windData)
                h, ws, wd = windData[:, 0], windData[:, 1], windData[:, 2]
                wx, wy = ws * np.sin(wd*np.pi/180), ws * np.cos(wd*np.pi/180)
                self.windSpeed = Function(np.column_stack((h, ws)), 'Height (m)', 'Wind Speed (m/s)')
                self.windHeading = Function(np.column_stack((h, wd)), 'Height (m)', 'Wind Heading (deg)')
                self.windVelocityX = Function(np.column_stack((h, wx)), 'Height (m)', 'Wind Velocity X (m/s)')
                self.windVelocityY = Function(np.column_stack((h, wy)), 'Height (m)', 'Wind Velocity y (m/s)')
                self.maxExpectedHeight = windData[-1, 0]
            # Throw error if array input not recognized
            else:
                raise TypeError('Only arrays of length 2  and matrices (Nx3) '
                                'are accepted.')
        return None

    def allInfo(self):
        """Prints out all data and graphs available about the Environment.

        Parameters
        ----------
        None
        
        Return
        ------
        None
        """
        # Print gravity details
        print('Gravity Details')
        print('Acceleration of Gravity: ' + str(self.g) + ' m/s2')

        # Print rail details
        print('\nRail Details')
        print('Rail Length: ' + str(self.rL) + ' m')

        # Print spacetime details
        if self.date is not None or self.lat is not None:
            print('\nSpacetime Details')
            if self.date is not None:
                print('Date: ', self.date)
            if self.lat is not None:
                print('Latitude: ', self.lat)
                print('Longitude: ', self.lon)

        # Show plots
        print('\nWind Plots')
        self.windHeading.plot(0, self.maxExpectedHeight)
        self.windSpeed.plot(0, self.maxExpectedHeight)
        self.windVelocityX.plot(0, self.maxExpectedHeight)
        self.windVelocityY.plot(0, self.maxExpectedHeight)
        print('\n Standard Atmosphere Plots')
        self.pressure.plot(0, 4000)
        self.temperature.plot(0, 4000)
        self.speedOfSound.plot(0, 4000)
        self.density.plot(0, 4000)

    def info(self):
        """Prints most important data and graphs available about the Environment.

        Parameters
        ----------
        None
        
        Return
        ------
        None
        """
        # Print rail details
        print('\nRail Details')
        print('Rail Length: ' + str(self.rL) + ' m')

        # Print spacetime details
        if self.date is not None:
            print('\nSpacetime Details')
            if self.date is not None:
                print('Date: ', self.date)

        # Show plots
        print('\nWind Plots')
        self.windHeading.plot(0, self.maxExpectedHeight)
        self.windSpeed.plot(0, self.maxExpectedHeight)

    def processNetCDFFile(self, windData):
        """Process netCDF File and store atmospheric data to be used.
        
        Parameters
        ----------
        windData : netCDF4 Dataset
            Dataset containing atmospheric data
        
        Return
        ------
        None
        """
        # Check if date, lat and lon is know
        if self.date is None:
            raise TypeError('Please specify Date (array-like).')
        if self.lat is None:
            raise TypeError('Please specify Location (lat, lon).')

        # Get data from file
        times = windData.variables['time']
        lons = windData.variables['longitude']
        lats = windData.variables['latitude']
        levels = windData.variables['level']
        geopotentials = windData.variables['z']
        windUs = windData.variables['u']
        windVs = windData.variables['v']

        # Find time index
        timeIndex = netCDF4.date2index(self.date, times, select='nearest')

        # Find longitude index
        lon = self.lon%360
        lonIndex = None
        for i in range(1, len(lons)):
            # Determine if longitude is between lons[i - 1] and lons[i]
            if (lons[i - 1] - lon)*(lon - lons[i]) >= 0:
                lonIndex = i
        if lonIndex is None:
            raise ValueError('Longitude not inside region covered by file.')

        # Find latitude index
        latIndex = None
        for i in range(1, len(lats)):
            # Determine if longitude is between lons[i - 1] and lons[i]
            if (lats[i - 1] - self.lat)*(self.lat - lats[i]) >= 0:
                latIndex = i
        if latIndex is None:
            raise ValueError('Latitude not inside region covered by file.')

        # Determine wind u and v components and height
        windU = []
        for i in range(len(levels)):
            windU.append(windUs[timeIndex, i, latIndex, lonIndex])
        windV = []
        for i in range(len(levels)):
            windV.append(windVs[timeIndex, i, latIndex, lonIndex])
        height = []
        for i in range(len(levels)):
            height.append(geopotentials[timeIndex, i, latIndex, lonIndex]/self.g)

        # Convert wind data into functions
        self.windVelocityX = Function(np.array([height, windU]).T,
                                      'Height (m)', 'Wind Velocity X (m/s)',
                                      extrapolation='constant')
        self.windVelocityY = Function(np.array([height, windV]).T,
                                      'Height (m)', 'Wind Velocity y (m/s)',
                                      extrapolation='constant')
        # Calculate wind heading and velocity magnitude
        windHeading = (180/np.pi)*np.arctan2(windU, windV)%360
        windSpeed = (np.array(windU)**2 + np.array(windV)**2)**0.5
        self.windHeading = Function(np.array([height, windHeading]).T,
                                    'Height (m)', 'Wind Heading (degrees)',
                                    extrapolation='constant')
        self.windSpeed = Function(np.array([height, windSpeed]).T,
                                  'Height (m)', 'Wind Speed (m/s)',
                                  extrapolation='constant')
        
        # Store data
        self.lats = lats
        self.lons = lons
        self.lonIndex = lonIndex
        self.latIndex = latIndex
        self.geopotentials = geopotentials
        self.windUs = windUs
        self.windVs = windVs
        self.levels = levels
        self.times = times
        self.height = height
        self.maxExpectedHeight = height[0]

        return None

    def reprocessNetCDFFile(self):
        """Reprocess netCDF File after date and/or location update
        and store atmospheric data to be used.
        
        Parameters
        ----------
        None
        
        Return
        ------
        None
        """
        # Restore data
        lats = self.lats
        lons = self.lons
        lonIndex = self.lonIndex
        latIndex = self.latIndex
        geopotentials = self.geopotentials
        windUs = self.windUs
        windVs = self.windVs
        levels = self.levels
        times = self.times

        # Find time index
        timeIndex = netCDF4.date2index(self.date, times, select='nearest')

        # Determine wind u and v components and height
        windU = []
        for i in range(len(levels)):
            windU.append(windUs[timeIndex, i, latIndex, lonIndex])
        windV = []
        for i in range(len(levels)):
            windV.append(windVs[timeIndex, i, latIndex, lonIndex])

        # Convert wind data into functions
        self.windVelocityX = Function(np.array([self.height, windU]).T,
                                      'Height (m)', 'Wind Velocity X (m/s)', extrapolation='constant')
        self.windVelocityY = Function(np.array([self.height, windV]).T,
                                      'Height (m)', 'Wind Velocity y (m/s)', extrapolation='constant')

        # Calculate wind heading and velocity magnitude
        windHeading = (180/np.pi)*np.arctan2(windU, windV)%360
        windSpeed = (np.array(windU)**2 + np.array(windV)**2)**0.5
        self.windHeading = Function(np.array([height, windHeading]).T,
                                    'Height (m)', 'Wind Heading (degrees)',
                                    extrapolation='constant')
        self.windSpeed = Function(np.array([height, windSpeed]).T,
                                  'Height (m)', 'Wind Speed (m/s)',
                                  extrapolation='constant')
        
        return None

    def addWindGust(self, windGustX, windGustY):
        """ Adds a function to the current stored wind profile, in order to
        simulate a wind gust.

        Parameters
        ----------
        windGustX : float, callable
            Callable, function of altitude, which will be added to the
            x velocity of the current stored wind profile. If float is given,
            it will be considered as a constant function in altitude.
        windGustY : float, callable
            Callable, function of altitude, which will be added to the
            y velocity of the current stored wind profile. If float is given,
            it will be considered as a constant function in altitude.

        Returns
        -------
        None
        """
        # Recalculate windVelocityX and windVelocityY
        self.windVelocityX = self.windVelocityX + windGustX
        self.windVelocityY = self.windVelocityY + windGustY

        # Reset windVelocityX and windVelocityY details
        self.windVelocityX.setInputs('Height (m)')
        self.windVelocityX.setOutputs('Wind Velocity X (m/s)')
        self.windVelocityY.setInputs('Height (m)')
        self.windVelocityY.setOutputs('Wind Velocity Y (m/s)')

        # Reset wind heading and velocity magnitude
        self.windHeading = Function(lambda h: (180/np.pi)*np.arctan2(self.windVelocityX(h), self.windVelocityY(h))%360,
                                    'Height (m)', 'Wind Heading (degrees)',
                                    extrapolation='constant')
        self.windSpeed = Function(lambda h: (self.windVelocityX(h)**2 + self.windVelocityY(h)**2)**0.5,
                                  'Height (m)', 'Wind Speed (m/s)',
                                  extrapolation='constant')
        
        return None

    def setDate(self, date):
        """Set date and time of launch and update weather conditions if
        available.
        
        Parameters
        ----------
        date : Date
            Date object specifying launch date and time.
        
        Return
        ------
        None
        """
        self.date = datetime(*date)
        if self.windDataSource == 'netCDF':
            self.reprocessNetCDFFile()
        
        return None


class Motor:
    """Class to specify characteriscts and useful operations for solid
    motors.
    
    Class attributes
    ----------------
    
        Geometrical attributes:
        Motor.nozzleRadius : float
            Radius of motor nozzle outlet in meters.
        Motor.throatRadius : float
            Radius of motor nozzle throat in meters.
        Motor.grainNumber : int
            Number os solid grains.
        Motor.grainSeparation : float
            Distance between two grains in meters.
        Motor.grainDensity : float
            Density of each grain in kg/meters cubed.
        Motor.grainOuterRadius : float
            Outer radius of each grain in meters.
        Motor.grainInitialInnerRadius : float
            Initial inner radius of each grain in meters.
        Motor.grainInitialHeight : float
            Initial height of each grain in meters.
        Motor.grainInitialVolume : float
            Initial volume of each grain in meters cubed.
        Motor.grainInnerRadius : Function
            Inner radius of each grain in meters as a function of time.
        Motor.grainHeight : Function
            Height of each grain in meters as a function of time.

        Mass and moment of inertia attributes:
        Motor.grainInitialMass : float
            Initial mass of each grain in kg.
        Motor.propellantInitialMass : float
            Total propellant initial mass in kg.
        Motor.mass : Function
            Propellant total mass in kg as a function of time.
        Motor.massDot : Function
            Time derivative of propellant total mass in kg/s as a function
            of time.
        Motor.inertiaI : Function
            Propellant moment of inertia in kg*meter^2 with respect to axis
            perpendicular to axis of cylindrical symmetry of each grain,
            given as a function of time.
        Motor.inertiaIDot : Function
            Time derivative of inertiaI given in kg*meter^2/s as a function
            of time.
        Motor.inertiaZ : Function
            Propellant moment of inertia in kg*meter^2 with respect to axis of
            cylindrical symmetry of each grain, given as a function of time.
        Motor.inertiaDot : Function
            Time derivative of inertiaZ given in kg*meter^2/s as a function
            of time.   
        
        Thrust and burn attributes:
        Motor.thrust : Function
            Motor thrust force, in Newtons, as a function of time.
        Motor.totalImpulse : float
            Total impulse of the thrust curve in N*s.
        Motor.maxThrust : float
            Maximum thrust value of the given thrust curve, in N.
        Motor.maxThrustTime : float
            Time, in seconds, in which the maximum thrust value is achieved.
        Motor.averageThrust : float
            Average thrust of the motor, given in N.
        Motor.burnOutTime : float
            Total motor burn out time, in seconds. Must include delay time
            when motor takes time to ignite. Also seen as time to end thrust
            curve.
        Motor.exhaustVelocity : float
            Propulsion gases exhaust velocity, assumed constant, in m/s.
        Motor.burnArea : Function
            Total burn area considering all grains, made out of inner
            cylindrical burn area and grain top and bottom faces. Expressed
            in meters squared as a function of time.
        Motor.Kn : Function
            Motor Kn as a function of time. Defined as burnArea divided by
            nozzle throat cross sectional area. Has no units.
        Motor.burnRate : Function
            Propellant burn rate in meter/second as a function of time.
        Motor.interpolate : string
            Method of interpolation used in case thrust curve is given
            by data set in .csv or .eng, or as an array. Options are 'spline'
            'akima' and 'linear'. Default is "linear".
    """
    def __init__(self,
                 thrustSource,
                 burnOut,
                 grainNumber,
                 grainDensity,
                 grainOuterRadius,
                 grainInitialInnerRadius,
                 grainInitialHeight,
                 grainSeparation=0,
                 nozzleRadius=0.0335,
                 throatRadius=0.0114,
                 reshapeThrustCurve=False,
                 interpolationMethod='linear'):
        """Initialize Motor class, process thrust curve and geometrical
        parameters and store results.

        Parameters
        ----------
        thrustSource : int, float, callable, string, array
            Motor's thrust curve. Can be given as an int or float, in which
            case the thrust will be considerared constant in time. It can
            also be given as a callable function, whose argument is time in
            seconds and returns the thrust supplied by the motor in the
            instant. If a string is given, it must point to a .csv or .eng file.
            The .csv file shall contain no headers and the first column must
            specify time in seconds, while the second column specifies thrust.
            Arrays may also be specified, following rules set by the class
            Function. See help(Function). Thrust units is Newtons.
        burnOut : int, float
            Motor burn out time in seconds.
        grainNumber : int
            Number of solid grains
        grainDensity : int, float
            Solid grain density in kg/m3.
        grainOuterRadius : int, float
            Solid grain outer radius in meters.
        grainInitialInnerRadius : int, float
            Solid grain initial inner radius in meters.
        grainInitialHeight : int, float
            Solid grain initial height in meters.
        grainSeparation : int, float, optional
            Distance between grains, in meters. Default is 0.
        nozzleRadius : int, float, optional
            Motor's nozzle outlet radius in meters. Used to calculate Kn curve.
            Optional if Kn curve is not if intereste. Its value does not impact
            trajectory simulation.
        throatRadius : int, float, optional
            Motor's nozzle throat radius in meters. Its value has very low
            impact in trajectory simulation, only useful to analyze
            dynamic instabilities, therefore it is optional. 
        reshapeThrustCurve : boolean, tuple, optional
            If False, the original thrust curve supplied is not altered. If a
            tuple is given, whose first parameter is a new burn out time and
            whose second parameter is a new total impulse in Ns, the thrust
            curve is reshaped to match the new specifications. May be useful
            for motors whose thrust curve shape is expected to remain similar
            in case the impulse and burn time varies slightly. Default is
            False.
        interpolationMethod : string, optional
            Method of interpolation to be used in case thrust curve is given
            by data set in .csv or .eng, or as an array. Options are 'spline'
            'akima' and 'linear'. Default is "linear".
        
        Returns
        -------
        None
        """
        # Thrust parameters
        self.interpolate = interpolationMethod
        self.burnOutTime = burnOut

        # Check if thrustSource is csv, eng, function or other
        if isinstance(thrustSource, str):
            # Determine if csv or eng
            if thrustSource[-3:] == 'eng':
                # Import content
                comments, desc, points = self.importEng(thrustSource)
                # Process description and points
                # diameter = float(desc[1])/1000
                # height = float(desc[2])/1000
                # mass = float(desc[4])
                # nozzleRadius = diameter/4
                # throatRadius = diameter/8
                # grainNumber = grainnumber
                # grainVolume = height*np.pi*((diameter/2)**2 -(diameter/4)**2)
                # grainDensity = mass/grainVolume
                # grainOuterRadius = diameter/2
                # grainInitialInnerRadius = diameter/4
                # grainInitialHeight = height
                thrustSource = points
                self.burnOutTime = points[-1][0]
       
        # Create thrust function
        self.thrust = Function(thrustSource, 'Time (s)', 'Thrust (N)',
                               self.interpolate, 'zero')
        if callable(thrustSource) or isinstance(thrustSource, (int, float)):
            self.thrust.setDiscrete(0, burnOut, 50, self.interpolate, 'zero')
       
        # Reshape curve and calculate impulse
        if reshapeThrustCurve:
            self.reshapeThrustCurve(*reshapeThrustCurve)
        else:
            self.evaluateTotalImpulse()
        
        # Define motor attributes
        # Grain and nozzle parameters
        self.nozzleRadius = nozzleRadius
        self.throatRadius = throatRadius
        self.grainNumber = grainNumber
        self.grainSeparation = grainSeparation
        self.grainDensity = grainDensity
        self.grainOuterRadius = grainOuterRadius
        self.grainInitialInnerRadius = grainInitialInnerRadius
        self.grainInitialHeight = grainInitialHeight
        # Other quantities that will be computed
        self.exhaustVelocity = None
        self.massDot = None
        self.mass = None
        self.grainInnerRadius = None
        self.grainHeight = None
        self.burnArea = None
        self.Kn = None
        self.burnRate = None
        self.inertiaI = None
        self.inertiaIDot = None
        self.inertiaZ = None
        self.inertiaDot = None
        self.maxThrust = None
        self.maxThrustTime = None
        self.averageThrust = None
        
        # Compute uncalculated quantities
        # Thrust information - maximum and average
        self.maxThrust = np.amax(self.thrust.source[:, 1])
        maxThrustIndex = np.argmax(self.thrust.source[:, 1])
        self.maxThrustTime = self.thrust.source[maxThrustIndex, 0]
        self.averageThrust = self.totalImpulse/self.burnOutTime
        # Grains initial geometrical parameters
        self.grainInitialVolume = (self.grainInitialHeight * np.pi *
                                   (self.grainOuterRadius**2 -
                                    self.grainInitialInnerRadius**2))
        self.grainInitialMass = self.grainDensity*self.grainInitialVolume
        self.propellantInitialMass = self.grainNumber*self.grainInitialMass
        # Dynamic quantities
        self.evaluateExhaustVelocity()
        self.evaluateMassDot()
        self.evaluateMass()
        self.evaluateGeometry()
        self.evaluateInertia()

    def reshapeThrustCurve(self, burnTime, totalImpulse,
                           oldTotalImpulse=None, startAtZero=True):
        """Transforms the thrust curve supplied by changing its total
        burn time and/or its total impulse, without altering the
        general shape of the curve. May translate the curve so that
        thrust starts at time equals 0, with out any delays.

        Parameters
        ----------
        burnTime : float
            New desired burn out time in seconds.
        totalImpulse : float
            New desired total impulse.
        oldTotalImpulse : float, optional
            Specify the total impulse of the given thrust curve,
            overriding the value calculated by numerical integration.
            If left as None, the value calculated by numerical
            integration will be used in order to reshape the curve.
        startAtZero: bool, optional
            If True, trims the initial thrust curve points which
            are 0 Newtons, translating the thrust curve so that
            thrust starts at time equals 0. If False, no translation
            is applied.
        
        Returns
        -------
        None
        """
        # Retrieve current thrust curve data points
        timeArray = self.thrust.source[:, 0]
        thrustArray = self.thrust.source[:, 1]

        # Move start to time = 0
        if startAtZero and timeArray[0] != 0:
            timeArray = timeArray - timeArray[0]

        # Reshape time - set burn time to burnTime
        self.thrust.source[:, 0] = (burnTime/timeArray[-1])*timeArray
        self.burnOutTime = burnTime
        self.thrust.setInterpolation(self.interpolate)

        # Reshape thrust - set total impulse
        if oldTotalImpulse is None:
            oldTotalImpulse = self.evaluateTotalImpulse()
        self.thrust.source[:, 1] = (totalImpulse/oldTotalImpulse)*thrustArray
        self.thrust.setInterpolation(self.interpolate)

        # Store total impulse
        self.totalImpulse = totalImpulse

        # Return reshaped curve
        return self.thrust

    def evaluateTotalImpulse(self):
        """Calculates and returns total impulse by numerical
        integration of the thrust curve in SI units. The value is
        also stored in self.totalImpulse.

        Parameters
        ----------
        None
        
        Returns
        -------
        self.totalImpulse : float
            Motor total impulse in Ns.
        """
        # Calculate total impulse
        self.totalImpulse = self.thrust.integral(0, self.burnOutTime)

        # Return total impulse
        return self.totalImpulse

    def evaluateExhaustVelocity(self):
        """Calculates and returns exhaust velocity by assuming it
        as a constant. The formula used is total impulse/propellant
        initial mass. The value is also stored in 
        self.exhaustVelocity.

        Parameters
        ----------
        None
        
        Returns
        -------
        self.exhaustVelocity : float
            Constant gas exhaust velocity of the motor.
        """
        # Calculate total impulse if not yet done so
        if self.totalImpulse is None:
            self.evaluateTotalImpulse()

        # Calculate exhaust velocity
        self.exhaustVelocity = self.totalImpulse/self.propellantInitialMass

        # Return exhaust velocity
        return self.exhaustVelocity

    def evaluateMassDot(self):
        """Calculates and returns the time derivative of propellant
        mass by assuming constant exhaust velocity. The formula used
        is the opposite of thrust divided by exhaust velocity. The
        result is a function of time, object of the Function class,
        which is stored in self.massDot.

        Parameters
        ----------
        None
        
        Returns
        -------
        self.massDot : Function
            Time derivative of total propellant mas as a function
            of time.
        """
        # Calculate exhaust velocity if not done so already
        if self.exhaustVelocity is None:
            self.evaluateExhaustVelocity()

        # Create mass dot Function
        self.massDot = self.thrust/(-self.exhaustVelocity)
        self.massDot.setOutputs('Mass Dot (kg/s)')
        self.massDot.setExtrapolation('zero')

        # Return Function
        return self.massDot

    def evaluateMass(self):
        """Calculates and returns the total propellant mass curve by
        numerically integrating the MassDot curve, calculated in
        evaluateMassDot. Numerical integration is done with the
        Trapezoidal Rule, given the same result as scipy.integrate.
        odeint but 100x faster. The result is a function of time,
        object of the class Function, which is stored in self.mass.

        Parameters
        ----------
        None
        
        Returns
        -------
        self.mass : Function
            Total propellant mass as a function of time.
        """
        # Retrieve mass dot curve data
        t = self.massDot.source[:,0]
        ydot = self.massDot.source[:,1]

        # Set initial conditions
        T = [0]
        y = [self.propellantInitialMass]

        # Solve for each time point
        for i in range(1, len(t)):
            T += [t[i]]
            y += [y[i-1] + 0.5*(t[i] - t[i-1])*(ydot[i] + ydot[i-1])]

        # Create Function
        self.mass = Function(np.concatenate(([T], [y])).
                             transpose(), 'Time (s)',
                             'Propellant Total Mass (kg)', self.interpolate,
                             'constant')

        # Return Mass Function
        return self.mass

    def evaluateGeometry(self):
        """Calculates grain inner radius and grain height as a
        function of time by assuming that every propellant mass
        burnt is exhausted. In order to do that, a system of
        differential equations is solved using scipy.integrate.
        odeint. Furthermore, the function calculates burn area,
        burn rate and Kn as a function of time using the previous
        results. All functions are stored as objects of the class
        Function in self.grainInnerRadius, self.grainHeight, self.
        burnArea, self.burnRate and self.Kn.

        Parameters
        ----------
        None
        
        Returns
        -------
        geometry : list of Functions
            First element is the Function representing the inner
            radius of a grain as a function of time. Second
            argument is the Function representing the height of a
            grain as a function of time.
        """
        # Define initial conditions for integration
        y0 = [self.grainInitialInnerRadius, self.grainInitialHeight]

        # Define time mesh
        t = self.massDot.source[:, 0]

        # Define system of differential equations
        density = self.grainDensity
        rO = self.grainOuterRadius
        def geometryDot(y, t):
            grainMassDot = self.massDot(t)/self.grainNumber
            rI, h = y
            rIDot = -0.5*grainMassDot/(density*np.pi*(rO**2-rI**2+rI*h))
            hDot = 1.0*grainMassDot/(density*np.pi*(rO**2-rI**2+rI*h))
            return [rIDot, hDot]

        # Solve the system of differential equations
        sol = integrate.odeint(geometryDot, y0, t)

        # Write down functions for innerRadius and height
        self.grainInnerRadius = Function(np.concatenate(([t], [sol[:, 0]])).
                                         transpose().tolist(), 'Time (s)',
                                         'Grain Inner Radius (m)',
                                         self.interpolate, 'constant')
        self.grainHeight = Function(np.concatenate(([t], [sol[:, 1]])).
                                    transpose().tolist(),
                                    'Time (s)', 'Grain Height (m)',
                                    self.interpolate, 'constant')

        # Create functions describing burn rate, Kn and burn area
        # Burn Area
        self.burnArea = 2*np.pi*(self.grainOuterRadius**2 -
                                 self.grainInnerRadius**2 +
                                 self.grainInnerRadius *
                                 self.grainHeight)*self.grainNumber
        self.burnArea.setOutputs('Burn Area (m2)')
        # Kn
        throatArea = np.pi*(self.throatRadius)**2
        KnSource = (np.concatenate(([self.grainInnerRadius.source[:, 1]],
                                    [self.burnArea.source[:, 1]/throatArea]
                                    )).transpose()).tolist()
        self.Kn = Function(KnSource, 'Grain Inner Radius (m)',
                           'Kn (m2/m2)', self.interpolate, 'constant')
        # Burn Rate
        self.burnRate = (-1)*self.massDot/(self.burnArea*self.grainDensity)
        self.burnRate.setOutputs('Burn Rate (m/s)')

        return [self.grainInnerRadius, self.grainHeight]

    def evaluateInertia(self):
        """Calculates propellant inertia I, relative to directions
        perpendicular to the rocket body axis and its time derivative
        as a function of time. Also calculates propellant inertia Z,
        relative to the axial direction, and its time derivative as a
        function of time. Products of inertia are assumed null due to
        symmetry. The four functions are stored as an object of the
        Function class.

        Parameters
        ----------
        None
        
        Returns
        -------
        list of Functions
            The first argument is the Function representing inertia I,
            while the second argument is the Function representing
            inertia Z.
        """

        # Inertia I
        # Calculate inertia I for each grain
        grainMass = self.mass/self.grainNumber
        grainMassDot = self.massDot/self.grainNumber
        grainNumber = self.grainNumber
        grainInertiaI = grainMass*((1/4)*(self.grainOuterRadius**2 +
                                          self.grainInnerRadius**2) +
                                   (1/12)*self.grainHeight**2)

        # Calculate each grain's distance d to propellant center of mass
        initialValue = (grainNumber - 1)/2
        d = np.linspace(-initialValue, initialValue, self.grainNumber)
        d = d*(self.grainInitialHeight + self.grainSeparation)

        # Calculate inertia for all grains
        self.inertiaI = grainNumber*(grainInertiaI) + grainMass*np.sum(d**2)
        self.inertiaI.setOutputs('Propellant Inertia I (kg*m2)')

        # Inertia I Dot
        # Calculate each grain's inertia I dot
        grainInertiaIDot = (grainMassDot*((1/4)*(self.grainOuterRadius**2 +
                                                 self.grainInnerRadius**2) +
                                          (1/12)*self.grainHeight**2) +
                            grainMass*((1/2)*self.grainInnerRadius -
                                       (1/3)*self.grainHeight)*self.burnRate)

        # Calculate inertia I dot for all grains
        self.inertiaIDot = (grainNumber*(grainInertiaIDot) +
                            grainMassDot*np.sum(d**2))
        self.inertiaIDot.setOutputs('Propellant Inertia I Dot (kg*m2/s)')

        # Inertia Z
        self.inertiaZ = (1/2.0)*self.mass*(self.grainOuterRadius**2 +
                                           self.grainInnerRadius**2)
        self.inertiaZ.setOutputs('Propellant Inertia Z (kg*m2)')

        # Inertia Z Dot
        self.inertiaZDot = ((1/2.0)*(self.massDot*self.grainOuterRadius**2) +
                            (1/2.0)*(self.massDot*self.grainInnerRadius**2) +
                            self.mass*self.grainInnerRadius*self.burnRate)
        self.inertiaZDot.setOutputs('Propellant Inertia Z Dot (kg*m2/s)')

        return [self.inertiaI, self.inertiaZ]

    def importEng(self, fileName):
        """ Read content from .eng file and process it, in order to
        return the comments, description and data points.

        Parameters
        ----------
        fileName : string
            Name of the .eng file. E.g. 'test.eng'.
            Note that the .eng file must not contain the 0 0 point.

        Returns
        -------
        comments : list
            All comments in the .eng file, separeted by line in a list. Each
            line is an entry of the list.
        description: list
            Description of the motor. All attributes are returned separeted in
            a list. E.g. "F32 24 124 5-10-15 .0377 .0695 RV\n" is return as
            ['F32', '24', '124', '5-10-15', '.0377', '.0695', 'RV\n']
        dataPoints: list
            List of all data points in file. Each data point is an entry in
            the returned list and written as a list of two entries.
        """
        # Intiailize arrays
        comments = []
        description = []
        dataPoints = [[0, 0]]

        # Open and read .eng file
        with open(fileName) as file:
            for line in file:
                if line[0] == ';':
                    # Extract comment
                    comments.append(line)
                else:
                    if description == []:
                        # Extract description
                        description = line.split(' ')
                    else:
                        # Extract thrust curve data points
                        time, thrust = re.findall(r"[-+]?\d*\.\d+|[-+]?\d+", line)
                        dataPoints.append([float(time), float(thrust)])

        # Return all extract content
        return comments, description, dataPoints

    def exportEng(self, fileName, motorName):
        """ Exports thrust curve data points and motor description to
        .eng file format. A description of the format can be found
        here: http://www.thrustcurve.org/raspformat.shtml

        Parameters
        ----------
        fileName : string
            Name of the .eng file to be exported. E.g. 'test.eng'
        motorName : string
            Name given to motor. Will appear in the description of the
            .eng file. E.g. 'Mandioca'

        Returns
        -------
        None
        """
        # Open file
        file = open(fileName, 'w')

        # Write first line
        file.write(motorName + ' {:3.1f} {:3.1f} 0 {:2.3} {:2.3} PJ \n'
                   .format(2000*self.grainOuterRadius,
                           1000*self.grainNumber*(self.grainInitialHeight+self.grainSeparation),
                           self.propellantInitialMass,
                           self.propellantInitialMass))
        
        # Write thrust curve data points
        for item in self.thrust.source[:-1, :]:
            time = item[0]
            thrust = item[1]
            file.write('{:.4f} {:.3f}\n'.format(time, thrust))
        
        # Write last line
        file.write('{:.4f} {:.3f}\n'.format(self.thrust.source[-1, 0], 0))

        # Close file
        file.close()
        
        return None

    def info(self):
        """Prints out a summary of the data and graphs available about
        the Motor.

        Parameters
        ----------
        None
        
        Return
        ------
        None
        """
        # Print motor details
        print('\nMotor Details')
        print('Total Burning Time: ' + str(self.burnOutTime) + ' s')
        print('Total Propellant Mass: ' +
              "{:.3f}".format(self.propellantInitialMass) + ' kg')
        print('Propellant Exhaust Velocity: ' +
              "{:.3f}".format(self.exhaustVelocity) + ' m/s')
        print('Average Thrust: ' + "{:.3f}".format(self.averageThrust) + ' N')
        print('Maximum Thrust: ' + str(self.maxThrust) + ' N at ' +
              str(self.maxThrustTime) + ' s after ignition.')
        print('Total Impulse: ' + "{:.3f}".format(self.totalImpulse) + ' Ns')

        # Show plots
        print('\nPlots')
        self.thrust()
    
        return None

    def allInfo(self):
        """Prints out all data and graphs available about the Motor.

        Parameters
        ----------
        None
        
        Return
        ------
        None
        """
        # Print nozzle details
        print('Nozzle Details')
        print('Nozzle Radius: ' + str(self.nozzleRadius) + ' m')
        print('Nozzle Throat Radius: ' + str(self.throatRadius) + ' m')

        # Print grain details
        print('\nGrain Details')
        print('Number of Grains: ' + str(self.grainNumber))
        print('Grain Spacing: ' + str(self.grainSeparation) + ' m')
        print('Grain Density: ' + str(self.grainDensity) + ' kg/m3')
        print('Grain Outer Radius: ' + str(self.grainOuterRadius) + ' m')
        print('Grain Inner Radius: ' + str(self.grainInitialInnerRadius) +
              ' m')
        print('Grain Height: ' + str(self.grainInitialHeight) + ' m')
        print('Grain Volume: ' + "{:.3f}".format(self.grainInitialVolume) +
              ' m3')
        print('Grain Mass: ' + "{:.3f}".format(self.grainInitialMass) + ' kg')

        # Print motor details
        print('\nMotor Details')
        print('Total Burning Time: ' + str(self.burnOutTime) + ' s')
        print('Total Propellant Mass: ' +
              "{:.3f}".format(self.propellantInitialMass) + ' kg')
        print('Propellant Exhaust Velocity: ' +
              "{:.3f}".format(self.exhaustVelocity) + ' m/s')
        print('Average Thrust: ' + "{:.3f}".format(self.averageThrust) + ' N')
        print('Maximum Thrust: ' + str(self.maxThrust) + ' N at ' +
              str(self.maxThrustTime) + ' s after ignition.')
        print('Total Impulse: ' + "{:.3f}".format(self.totalImpulse) + ' Ns')

        # Show plots
        print('\nPlots')
        self.thrust()
        self.mass()
        self.massDot()
        self.grainInnerRadius()
        self.grainHeight()
        self.burnRate()
        self.burnArea()
        self.Kn()
        self.inertiaI()
        self.inertiaIDot()
        self.inertiaZ()
        self.inertiaZDot()
    
        return None


class Rocket:
    
    """Keeps all rocket and parachute information.

    Class attributes
    ----------------
        Geometrical attributes:
        Rocket.radius : float
            Rocket's largest radius in meters.
        Rocket.area : float
            Rocket's circular cross section largest frontal area in meters
            squared.
        Rocket.distanceRocketNozzle : float
            Distance between rocket's center of mass, without propellant,
            to the exit face of the nozzle, in meters. Always positive.
        Rocket.distanceRocketPropellant : float
            Distance between rocket's center of mass, without propellant,
            to the center of mass of propellant, in meters. Always positive.
        
        Mass and Inertia attributes:
        Rocket.mass : float
            Rocket's mass without propellant in kg.
        Rocket.inertiaI : float
            Rocket's moment of inertia, without propellant, with respect to
            to an axis perpendicular to the rocket's axis of cylindrical
            symmetry, in kg*m^2.
        Rocket.inertiaZ : float
            Rocket's moment of inertia, without propellant, with respect to
            the rocket's axis of cylindrical symmetry, in kg*m^2.
        Rocket.centerOfMass : Function
            Distance of the rocket's center of mass, including propellant,
            to rocket's center of mass without propellant, in meters.
            Expressed as a function of time.
        Rocket.reducedMass : Function
            Function of time expressing the reduced mass of the rocket,
            defined as the product of the propellant mass and the mass
            of the rocket without propellant, divided by the sum of the
            propellant mass and the rocket mass.
        Rocket.totalMass : Function
            Function of time expressing the total mass of the rocket,
            defined as the sum of the propellant mass and the rocket
            mass without propellant.

        Excentricity attributes:
        Rocket.cpExcentricityX : float
            Center of pressure position relative to center of mass in the x
            axis, perpendicular to axis of cylindrical symmetry, in meters. 
        Rocket.cpExcentricityY : float
            Center of pressure position relative to center of mass in the y
            axis, perpendicular to axis of cylindrical symmetry, in meters. 
        Rocket.thrustExcentricityY : float
            Thrust vector position relative to center of mass in the y
            axis, perpendicular to axis of cylindrical symmetry, in meters. 
        Rocket.thrustExcentricityX : float 
            Thrust vector position relative to center of mass in the x
            axis, perpendicular to axis of cylindrical symmetry, in meters. 
        
        Parachute attributes:
        Rocket.parachutes : list
            List of parachutes of the rocket.
            Each parachute has the following attributes:
            name : string
                Parachute name, such as drogue and main. Has no impact in
                simulation, as it is only used to display data in a more
                organized matter.
            CdS : float
                Drag coefficient times reference area for parachute. It is
                used to compute the drag force exerted on the parachute by
                the equation F = ((1/2)*rho*V^2)*CdS, that is, the drag
                force is the dynamic pressure computed on the parachute
                times its CdS coefficient. Has units of area and must be
                given in meters squared.
            trigger : function
                Function which defines if the parachute ejection system is
                to be triggered. It must take as input the freestream
                pressure in pascal and the state vector of the simulation,
                which is defined by [x, y, z, vx, vy, vz, e0, e1, e2, e3, wx, wy, wz].
                It will be called according to the sampling rate given next.
                It should return True if the parachute ejection system is
                to be triggered and False otherwise.
            samplingRate : float, optional
                Sampling rate in which the trigger function works. It is used to
                simulate the refresh rate of onboard sensors such as barometers.
                Default value is 100. Value must be given in Hertz.
            lag : float, optional
                Time between the parachute ejection system is triggered and the
                parachute is fully opened. During this time, the simulation will
                consider the rocket as flying without a parachute. Default value
                is 0. Must be given in seconds.
            noise : tupple, list, optional
                List in the format (mean, standard deviation, time-correlation).
                The values are used to add noise to the pressure signal which is
                passed to the trigger function. Default value is (0, 0, 0). Units
                are in Pascal.
            noiseSignal : list
                List of (t, noise signal) corresponding to signal passed to
                trigger function. Completed after running a simulation.
            noisyPressureSignal : list
                List of (t, noisy pressure signal) that is passed to the
                trigger function. Completed after running a simulation.
            cleanPressureSignal : list
                List of (t, clean pressure signal) corresponding to signal passed to
                trigger function. Completed after running a simulation.
            noiseSignalFunction : Function
                Function of noiseSignal.
            noisyPressureSignalFunction : Function
                Function of noisyPressureSignal.
            cleanPressureSignalFunction : Function
                Function of cleanPressureSignal.

       
        Aerodynamic attributes
        Rocket.aerodynamicSurfaces : list
            List of aerodynamic surfaces of the rocket.
        Rocket.staticMargin : float
            Float value corresponding to rocket static margin when
            loaded with propellant in units of rocket diameter or
            calibers.
        Rocket.powerOffDrag : Function
            Rocket's drag coefficient as a function of Mach number when the
            motor is off.
        Rocket.powerOnDrag : Function
            Rocket's drag coefficient as a function of Mach number when the
            motor is on.
        
        Motor attributes:
        Rocket.motor : Motor
            Rocket's motor. See Motor class for more details.
    """
    def __init__(self,
                 motor,
                 mass,
                 inertiaI,
                 inertiaZ,
                 radius,
                 distanceRocketNozzle,
                 distanceRocketPropellant,
                 powerOffDrag,
                 powerOnDrag):
        """Initialize Rocket class, process inertial, geometrical and
        aerodynamic parameters.

        Parameters
        ----------
        motor : Motor
            Motor used in the rocket. See Motor class for more information.
        mass : int, float
            Unloaded rocket total mass (without propelant) in kg.
        inertiaI : int, float
            Unloaded rocket lateral (perpendicular to axis of symmetry)
            moment of inertia (without propelant) in kg m^2.
        inertiaZ : int, float
            Unloaded rocket axial moment of inertia (without propelant)
            in kg m^2.
        radius : int, float
            Rocket biggest outer radius in meters.
        distanceRocketNozzle : int, float
            Distance from rocket's unloaded center of mass to nozzle outlet,
            in meters.
        distanceRocketPropellant : int, float
            Distance from rocket's unloaded center of mass to propellant
            center of mass, in meters.
        powerOffDrag : int, float, callable, string, array
            Rockets drag coefficient when the motor is off. Can be given as an
            entry to the Function class. See help(Function) for more
            information. If int or float is given, it is assumed constant. If
            callable, string or array is given, it must be a function o Mach
            number only.
        powerOnDrag : int, float, callable, string, array
            Rockets drag coefficient when the motor is on. Can be given as an
            entry to the Function class. See help(Function) for more
            information. If int or float is given, it is assumed constant. If
            callable, string or array is given, it must be a function o Mach
            number only.
        
        Returns
        -------
        None
        """
        # Define rocket inertia attributes in SI units
        self.mass = mass
        self.inertiaI = inertiaI
        self.inertiaZ = inertiaZ
        self.centerOfMass = (distanceRocketPropellant*motor.mass /
                             (mass + motor.mass))

        # Define rocket geometrical parameters in SI units
        self.radius = radius
        self.area = np.pi*self.radius**2

        # Center of mass distance to points of interest
        self.distanceRocketNozzle = distanceRocketNozzle
        self.distanceRocketPropellant = distanceRocketPropellant
        
        # Define excentricity
        self.cpExcentricityX = 0
        self.cpExcentricityY = 0
        self.thrustExcentricityY = 0
        self.thrustExcentricityX = 0


        # Parachute data initialization
        self.parachutes = []

        # Aerodynamic data initialization
        self.aerodynamicSurfaces = []

        # Define aerodynamic drag coefficients
        self.powerOffDrag = Function(powerOffDrag, 'Mach Number',
                                     'Drag Coefficient with Power Off',
                                     'spline', 'constant')
        self.powerOnDrag = Function(powerOnDrag, 'Mach Number',
                                    'Drag Coefficient with Power On',
                                    'spline', 'constant')

        # Define motor to be used
        self.motor = motor

        # Important dynamic inertial quantities
        self.reducedMass = None
        self.totalMass = None

        # Calculate dynamic inertial quantities
        self.evaluateReducedMass()
        self.evaluateTotalMass()

        return None

    def evaluateReducedMass(self):
        """Calculates and returns the rocket's total reduced mass. The
        reduced mass is defined as the product of the propellant mass
        and the mass of the rocket with outpropellant, divided by the
        sum of the propellant mass and the rocket mass. The function
        returns a object of the Function class and is defined as a
        function of time. 

        Parameters
        ----------
        None
        
        Returns
        -------
        self.reducedMass : Function
            Function of time expressing the reduced mass of the rocket,
            defined as the product of the propellant mass and the mass
            of the rocket without propellant, divided by the sum of the
            propellant mass and the rocket mass.
        """
        # Make sure there is a motor associated with the rocket
        if self.motor is None:
            print('Please associate this rocket with a motor!')
            return False
        
        # Retrieve propellant mass as a function of time
        motorMass = self.motor.mass

        # Retrieve constant rocket mass with out propellant
        mass = self.mass

        # Calculate reduced mass
        self.reducedMass = motorMass*mass/(motorMass+mass)
        self.reducedMass.setOutputs('Reduced Mass (kg)')

        # Return reduced mass
        return self.reducedMass

    def evaluateTotalMass(self):
        """Calculates and returns the rocket's total mass. The total
        mass is defined as the sum of the propellant mass and the
        rocket mass without propellant. The function returns an object
        of the Function class and is defined as a function of time. 

        Parameters
        ----------
        None
        
        Returns
        -------
        self.totalMass : Function
            Function of time expressing the total mass of the rocket,
            defined as the sum of the propellant mass and the rocket
            mass without propellant.
        """
        # Make sure there is a motor associated with the rocket
        if self.motor is None:
            print('Please associate this rocket with a motor!')
            return False
        
        # Calculate total mass by summing up propellant and dry mass
        self.totalMass = self.mass + self.motor.mass
        self.totalMass.setOutputs('Total Mass (Rocket + Propellant) (kg)')

        # Return total mass
        return self.totalMass

    def evaluateStaticMargin(self):
        """Calculates and returns the rocket's static margin when
        loaded with propellant. The static margin is saved and returned
        in units of rocket diameter or calibers. 

        Parameters
        ----------
        None
        
        Returns
        -------
        self.staticMargin : float
            Float value corresponding to rocket static margin when
            loaded with propellant in units of rocket diameter or
            calibers.
        """
        # Initialize total lift coeficient derivative and center of pressure
        self.totalLiftCoeffDer = 0
        self.cpPosition = 0

        # Calculate total lift coeficient derivative and center of pressure   
        if len(self.aerodynamicSurfaces) > 0:     
            for aerodynamicSurface in self.aerodynamicSurfaces:
                self.totalLiftCoeffDer += aerodynamicSurface[1]
                self.cpPosition += aerodynamicSurface[1]*aerodynamicSurface[0][2]
            self.cpPosition /= self.totalLiftCoeffDer

        # Calculate static margin
        self.staticMargin = ((self.centerOfMass - self.cpPosition) /
                             (2*self.radius))
        self.staticMargin.setInputs('Time (s)')
        self.staticMargin.setOutputs('Static Margin (c)')
        
        # Return self
        return self

    def addTail(self, topRadius, bottomRadius, length, distanceToCM):
        """Create a new tail or rocket diameter change, storing its
        parameters as part of the aerodynamicSurfaces list. Its
        parameters are the axial position along the rocket and its
        derivative of the coefficient of lift in respect to angle of
        attack.

        Parameters
        ----------
        topRadius : int, float
            Tail top radius in meters, considering positive direction
            from center of mass to nose cone.
        bottomRadius : int, float
            Tail bottom radius in meters, considering positive direction
            from center of mass to nose cone.
        length : int, float
            Tail length or height in meters. Must be a positive value.
        distanceToCM : int, float
            Tail position relative to rocket unloaded center of mass,
            considering positive direction from center of mass to nose
            cone. Consider the point belonging to the tail which is
            closest to the unloaded center of mass to calculate
            distance.

        Returns
        -------
        self : Rocket
            Object of the Rocket class.
        """
        # Calculate ratio between top and bottom radius
        r = topRadius/bottomRadius

        # Retrieve reference radius
        rref = self.radius

        # Calculate cp position relative to cm
        if distanceToCM < 0:
            cpz = distanceToCM - (length/3)*(1 + (1-r)/(1 - r**2))
        else:
            cpz = distanceToCM + (length/3)*(1 + (1-r)/(1 - r**2))
        
        # Calculate clalpha
        clalpha = -2*(1 - r**(-2))*(topRadius/rref)**2
        
        # Store values as new aerodynamic surface
        tail = [(0, 0, cpz), clalpha, 'Tail']
        self.aerodynamicSurfaces.append(tail)

        # Refresh static margin calculation
        self.evaluateStaticMargin()

        # Return self
        return self.aerodynamicSurfaces[-1]

    def addNose(self, length, kind, distanceToCM):
        """Create a nose cone, storing its parameters as part of the
        aerodynamicSurfaces list. Its parameters are the axial position
        along the rocket and its derivative of the coefficient of lift
        in respect to angle of attack.


        Parameters
        ----------
        length : int, float
            Nose cone length or height in meters. Must be a postive
            value.
        kind : string
            Nose cone type. Von Karman, conical, ogive, and lvhaack are
            supported.
        distanceToCM : int, float
            Nose cone position relative to rocket unloaded center of
            mass, considering positive direction from center of mass to
            nose cone. Consider the center point belonging to the nose
            cone base to calculate distance.

        Returns
        -------
        self : Rocket
            Object of the Rocket class.
        """
        # Analyze type
        if kind == 'conical':
            k = 1 - 1/3
        elif kind == 'ogive':
            k = 1 - 0.534
        elif kind == 'lvhaack':
            k = 1 - 0.437
        else:
            k = 0.5

        # Calculate cp position relative to cm
        if distanceToCM > 0:
            cpz = distanceToCM + k*length
        else:
            cpz = distanceToCM - k*length
        
        # Calculate clalpha
        clalpha = 2
        
        # Store values
        nose = [(0, 0, cpz), clalpha, 'Nose Cone']
        self.aerodynamicSurfaces.append(nose)
        
        # Refresh static margin calculation
        self.evaluateStaticMargin()

        # Return self
        return self.aerodynamicSurfaces[-1]

    def addFins(self, n, span, rootChord, tipChord, distanceToCM, radius=0):
        """Create a fin set, storing its parameters as part of the
        aerodynamicSurfaces list. Its parameters are the axial position
        along the rocket and its derivative of the coefficient of lift
        in respect to angle of attack.

        Parameters
        ----------
        n : int
            Number of fins, from 2 to infinity.
        span : int, float
            Fin span in meters.
        rootChord : int, float
            Fin root chord in meters.
        tipChord : int, float
            Fin tip chord in meters.
        distanceToCM : int, float
            Fin set position relative to rocket unloaded center of
            mass, considering positive direction from center of mass to
            nose cone. Consider the center point belonging to the top
            of the fins to calculate distance.
        radius : int, float, optional
            Reference radius to calculate lift coefficient. If 0, which
            is default, use rocket radius. Otherwise, enter the radius
            of the rocket in the section of the fins, as this impacts
            its lift coefficient.

        Returns
        -------
        self : Rocket
            Object of the Rocket class.
        """

        # Retrieve parameters for calculations
        Cr = rootChord
        Ct = tipChord
        Yr = rootChord + tipChord
        s = span
        Lf = np.sqrt((rootChord/2 - tipChord/2)**2 + span**2)
        radius = self.radius if radius == 0 else radius
        d = 2*radius

        # Calculate cp position relative to cm
        if distanceToCM < 0:
            cpz = distanceToCM - (((Cr - Ct)/3)*((Cr + 2*Ct)/(Cr + Ct)) +
                                  (1/6)*(Cr + Ct - Cr*Ct/(Cr + Ct)))
        else:
            cpz = distanceToCM + (((Cr - Ct)/3)*((Cr + 2*Ct)/(Cr + Ct)) +
                                  (1/6)*(Cr + Ct - Cr*Ct/(Cr + Ct)))
                                  
        # Calculate clalpha
        clalpha = (4*n*(s/d)**2)/(1 + np.sqrt(1 + (2*Lf/Yr)**2))
        clalpha *= (1 + radius/(s + radius))

        # Store values
        fin = [(0, 0, cpz), clalpha, 'Fins']
        self.aerodynamicSurfaces.append(fin)
        
        # Refresh static margin calculation
        self.evaluateStaticMargin()

        # Return self
        return self.aerodynamicSurfaces[-1]

    def addParachute(self, name, CdS, trigger, samplingRate=100, lag=0, noise=(0, 0, 0)):
        """Create a new parachute, storing its parameters such as
        opening delay, drag coefficients and trigger function.

        Parameters
        ----------
        name : string
            Parachute name, such as drogue and main. Has no impact in
            simulation, as it is only used to display data in a more
            organized matter.
        CdS : float
            Drag coefficient times reference area for parachute. It is
            used to compute the drag force exerted on the parachute by
            the equation F = ((1/2)*rho*V^2)*CdS, that is, the drag
            force is the dynamic pressure computed on the parachute
            times its CdS coefficient. Has units of area and must be
            given in meters squared.
        trigger : function
            Function which defines if the parachute ejection system is
            to be triggered. It must take as input the freestream
            pressure in pascal and the state vector of the simulation,
            which is defined by [x, y, z, vx, vy, vz, e0, e1, e2, e3, wx, wy, wz].
            It will be called according to the sampling rate given next.
            It should return True if the parachute ejection system is
            to be triggered and False otherwise.
        samplingRate : float, optional
            Sampling rate in which the trigger function works. It is used to
            simulate the refresh rate of onboard sensors such as barometers.
            Default value is 100. Value must be given in Hertz.
        lag : float, optional
            Time between the parachute ejection system is triggered and the
            parachute is fully opened. During this time, the simulation will
            consider the rocket as flying without a parachute. Default value
            is 0. Must be given in seconds.
        noise : tupple, list, optional
            List in the format (mean, standard deviation, time-correlation).
            The values are used to add noise to the pressure signal which is
            passed to the trigger function. Default value is (0, 0, 0). Units
            are in Pascal.
        
        Returns
        -------
        parachute : Parachute Object
            Parachute object containing trigger, samplingRate, lag, CdS, noise
            and name as attributes. Furthermore, it stores cleanPressureSignal,
            noiseSignal and noisyPressureSignal which is filled in during
            Flight simulation.
        """
        # Create an object to serve as the parachute
        parachute = type('', (), {})()

        # Store Cds coefficient, lag, name and trigger function
        parachute.trigger = trigger
        parachute.samplingRate = samplingRate
        parachute.lag = lag
        parachute.CdS = CdS
        parachute.name = name
        parachute.noiseBias = noise[0]
        parachute.noiseDeviation = noise[1]
        parachute.noiseCorr = (noise[2], (1-noise[2]**2)**0.5)
        alpha, beta = parachute.noiseCorr
        parachute.noiseFunction = lambda: alpha*parachute.noiseSignal[-1][1] + beta*np.random.normal(noise[0], noise[1])
        parachute.cleanPressureSignal = []
        parachute.noisyPressureSignal = []
        parachute.noiseSignal = [[-1e-6, np.random.normal(noise[0], noise[1])]]

        # Add parachute to list of parachutes
        self.parachutes.append(parachute)

        # Return self
        return  self.parachutes[-1]

    def addCMExcentricity(self, x, y):
        """Move line of action of aerodynamic and thrust forces by
        equal translation ammount to simulate an excentricity in the
        position of the center of mass of the rocket relative to its
        geometrical center line. Should not be used together with
        addCPExentricity and addThrustExentricity.

        Parameters
        ----------
        x : float
            Distance in meters by which the CM is to be translated in
            the x direction relative to geometrical center line.
        y : float
            Distance in meters by which the CM is to be translated in
            the y direction relative to geometrical center line.
        
        Returns
        -------
        self : Rocket
            Object of the Rocket class.
        """
        # Move center of pressure to -x and -y
        self.cpExcentricityX = -x
        self.cpExcentricityY = -y

        # Move thrust center by -x and -y
        self.thrustExcentricityY = -x
        self.thrustExcentricityX = -y

        # Return self
        return self
    
    def addCPExentricity(self, x, y):
        """Move line of action of aerodynamic forces to simulate an
        excentricity in the position of the center of pressure relative
        to the center of mass of the rocket.

        Parameters
        ----------
        x : float
            Distance in meters by which the CP is to be translated in
            the x direction relative to the center of mass axial line.
        y : float
            Distance in meters by which the CP is to be translated in
            the y direction relative to the center of mass axial line.
        
        Returns
        -------
        self : Rocket
            Object of the Rocket class.
        """
        # Move center of pressure by x and y
        self.cpExcentricityX = x
        self.cpExcentricityY = y

        # Return self
        return self

    def addThrustExentricity(self, x, y):
        """Move line of action of thrust forces to simulate a
        disalignment of the thrust vector and the center of mass.

        Parameters
        ----------
        x : float
            Distance in meters by which the the line of action of the
            thrust force is to be translated in the x direction
            relative to the center of mass axial line.
        y : float
            Distance in meters by which the the line of action of the
            thrust force is to be translated in the x direction
            relative to the center of mass axial line.
        
        Returns
        -------
        self : Rocket
            Object of the Rocket class.
        """
        # Move thrust line by x and y
        self.thrustExcentricityY = x
        self.thrustExcentricityX = y

        # Return self
        return self

    def info(self):
        """Prints out a summary of the data and graphs available about
        the Rocket.

        Parameters
        ----------
        None
        
        Return
        ------
        None
        """
        # Print inertia details
        print('Inertia Details')
        print('Rocket Dry Mass: ' + str(self.mass) + ' kg (No Propellant)')
        print('Rocket Total Mass: ' + str(self.totalMass(0)) + 
              ' kg (With Propellant)')

        # Print rocket geometrical parameters
        print('\nGeometrical Parameters')
        print('Rocket Radius: ' + str(self.radius) + ' m')

        # Print rocket aerodynamics quantities
        print('\nAerodynamics Stability')
        print('Initial Static Margin: ' +
              "{:.3f}".format(self.staticMargin(0)) + ' c')
        print('Final Static Margin: ' +
              "{:.3f}".format(self.staticMargin(self.motor.burnOutTime)) + ' c')

        # Print parachute data
        for chute in self.parachutes:
            print('\n' + chute.name.title() + ' Parachute')
            print('CdS Coefficient: ' + str(chute.CdS) + ' m2')

        # Show plots
        print('\nAerodynamics Plots')
        self.powerOnDrag()
    
        # Return None
        return None

    def allInfo(self):
        """Prints out all data and graphs available about the Rocket.

        Parameters
        ----------
        None
        
        Return
        ------
        None
        """
        # Print inertia details
        print('Inertia Details')
        print('Rocket Mass: ' + str(self.mass) + ' kg (No Propellant)')
        print('Rocket Mass: ' + str(self.totalMass(0)) + 
              ' kg (With Propellant)')
        print('Inertia I: ' + str(self.inertiaI) + ' kg*m2')
        print('Inertia Z: ' + str(self.inertiaZ) + ' kg*m2')

        # Print rocket geometrical parameters
        print('\nGeometrical Parameters')
        print('Rocket Radius: ' + str(self.radius) + ' m')
        print('Rocket Frontal Area: ' + "{:.6f}".format(self.area) + ' m2')
        print('\nRocket Distances')
        print('Rocket Center of Mass - Nozzle Exit Distance: ' +
              str(self.distanceRocketNozzle) + ' m')
        print('Rocket Center of Mass - Propellant Center of Mass Distance: ' +
              str(self.distanceRocketPropellant) + ' m')
        print('Rocket Center of Mass - Rocket Loaded Center of Mass: ' +
              "{:.3f}".format(self.centerOfMass(0)) + ' m')
        print('\nAerodynamic Coponents Parameters')
        print('Currently not implemented.')

        # Print rocket aerodynamics quantities
        print('\nAerodynamics Lift Coefficient Derivatives')
        for aerodynamicSurface in self.aerodynamicSurfaces:
            name = aerodynamicSurface[-1]
            clalpha = aerodynamicSurface[1]
            print(name + " Lift Coefficient Derivative: {:.3f}".format(clalpha)
                  + '/rad')
        
        print('\nAerodynamics Center of Pressure')
        for aerodynamicSurface in self.aerodynamicSurfaces:
            name = aerodynamicSurface[-1]
            cpz = aerodynamicSurface[0][2]
            print(name + " Center of Pressure to CM: {:.3f}".format(cpz)
                  + ' m')
        print('Distance - Center of Pressure to CM: ' +
              "{:.3f}".format(self.cpPosition) + ' m')
        print('Initial Static Margin: ' +
              "{:.3f}".format(self.staticMargin(0)) + ' c')
        print('Final Static Margin: ' +
              "{:.3f}".format(self.staticMargin(self.motor.burnOutTime)) + ' c')

        # Print parachute data
        for chute in self.parachutes:
            print('\n' + chute.name.title() + ' Parachute')
            print('CdS Coefficient: ' + str(chute.CdS) + ' m2')
            if chute.trigger.__name__ == '<lambda>':
                line = getsourcelines(chute.trigger)[0][0]
                print('Ejection signal trigger: ' +
                       line.split('lambda ')[1].split(',')[0].split('\n')[0])
            else:
                print('Ejection signal trigger: ' + chute.trigger.__name__)
            print('Ejection system refresh rate: ' +
                  str(chute.samplingRate) + ' Hz.')
            print('Time between ejection signal is triggered and the '
                  'parachute is fully opened: ' + str(chute.lag) + ' s')

        # Show plots
        print('\nMass Plots')
        self.totalMass()
        self.reducedMass()
        print('\nAerodynamics Plots')
        self.staticMargin()
        self.powerOnDrag()
        self.powerOffDrag()

        # Return None
        return None

    def addFin(self, numberOfFins=4, cl=2*np.pi, cpr=1, cpz=1,
               gammas=[0, 0, 0, 0], angularPositions=None):
        "Hey! I will document this function later"
        self.aerodynamicSurfaces = []
        pi = np.pi
        # Calculate angular postions if not given
        if angularPositions is None:
            angularPositions = np.array(range(numberOfFins))*2*pi/numberOfFins
        else:
            angularPositions = np.array(angularPositions)*pi/180
        # Convert gammas to degree
        if isinstance(gammas, (int, float)):
            gammas = [(pi/180)*gammas for i in range(numberOfFins)]
        else:
            gammas = [(pi/180)*gamma for gamma in gammas]
        for i in range(numberOfFins):
            # Get angular position and inclination for current fin
            angularPosition = angularPositions[i]
            gamma = gammas[i]
            # Calculate position vector
            cpx = cpr*np.cos(angularPosition)
            cpy = cpr*np.sin(angularPosition)
            positionVector = np.array([cpx, cpy, cpz])
            # Calculate chord vector
            auxVector = np.array([cpy, -cpx, 0])/(cpr)
            chordVector = (np.cos(gamma)*np.array([0, 0, 1]) -
                           np.sin(gamma)*auxVector)
            self.aerodynamicSurfaces.append([positionVector, chordVector])
        return None


class Flight:
    """Keeps all flight information and has a method to simulate flight.
    
    Class attributes
    ----------------
        Other classes:
        Flight.env : Environment
            Environment object describing rail length, gravity and
            weather condition. See Environment class for more details.
        Flight.rocket : Rocket
            Rocket class describing rocket. See Rocket class for more
            details.
        
        Simulation attributes:
        Flight.maxTime : int, float
            Maximum simulation time allowed. Refers to physical time
            being simulated, not time taken to run simulation.
        Flight.maxTimeStep : int, float
            Maximum step size to use during integration in seconds.
        Flight.terminateOnApogee : bool
            Wheater to terminate simulation when rocket reaches apogee.
        Flight.solution : list
            Solution array which keeps results from each numerical
            integration.
        Flight.tInitial : int, float
            Initial simulation time in seconds. Usually 0.
        Flight.solver : integrate.ode
            Scipy integration scheme.
        Flight.t : float
            Current integration time.
        Flight.y : list
            Current integration state vector u.
        Flight.noise : float
            Noise generated with normal distribution to feed parachute
            triggers.
        Flight.noiseFunction : Function
            Noise as a function of time.
        Flight.pFunction : Function
            Pressure supplied to parachutes trigger function as a
            function of time.
        Flight.simulating : bool
            Indicates while simulation is running or not.
        
        
        Solution monitor attributes:
        Flight.initialSolution : list
            List defininf initial condition - [self.tInitial, xInit,
            yInit, zInit, vxInit, vyInit, vzInit, e0Init, e1Init,
            e2Init, e3Init, w1Init, w2Init, w3Init]
        Flight.outOfRailTime : int, float
            Time, in seconds, in which the rocket completely leaves the
            rail.
        Flight.outOfRailState : list
            State vector u corresponding to state when the rocket
            completely leaves the rail.
        Flight.outOfRailVelocity : int, float
            Velocity, in m/s, with which the rocket completely leaves the
            rail.
        Flight.apogeeState : int, float
            State vector u corresponding to state when the rocket's
            vertical velocity is zero in the apogee.
        Flight.apogeeTime : int, float
            Time, in seconds, in which the rocket's vertical velocity
            reaches zero in the apogee.
        Flight.apogeeX : int, float
            X coordinate (positive east) of the center of mass of the
            rocket when it reaches apogee.
        Flight.apogeeY : int, float
            Y coordinate (positive north) of the center of mass of the
            rocket when it reaches apogee.
        Flight.apogee : int, float
            Z coordinate, or altitute, of the center of mass of the
            rocket when it reaches apogee.           
        Flight.xImpact : int, float
            X coordinate (positive east) of the center of mass of the
            rocket when it impacts ground.
        Flight.yImpact : int, float
            Y coordinate (positive east) of the center of mass of the
            rocket when it impacts ground.
        Flight.impactVelocity : int, float
            Velocity magnitude of the center of mass of the rocket when
            it impacts ground.
        Flight.flightPhases : list
            List with rocket flight phases, including event information.
        
        Solution attributes:
        Flight.x : Function
            Rocket's X coordinate (positive east) as a function of time.
        Flight.y : Function
            Rocket's Y coordinate (positive north) as a function of time.
        Flight.z : Function
            Rocket's z coordinate (positive up) as a function of time.
        Flight.vx : Function
            Rocket's X velocity as a function of time.
        Flight.vy : Function
            Rocket's Y velocity as a function of time.
        Flight.vz : Function
            Rocket's Z velocity as a function of time.
        Flight.e0 : Function
            Rocket's Euler parameter 0 as a function of time.
        Flight.e1 : Function
            Rocket's Euler parameter 1 as a function of time.
        Flight.e2 : Function
            Rocket's Euler parameter 2 as a function of time.
        Flight.e3 : Function
            Rocket's Euler parameter 3 as a function of time.
        Flight.w1 : Function
            Rocket's angular velocity Omega 1 as a function of time.
        Flight.w2 : Function
            Rocket's angular velocity Omega 2 as a function of time.
        Flight.w3 : Function
            Rocket's angular velocity Omega 3 as a function of time.
        
        Secondary attributes:
        Flight.maxVel : float
            Maximum velocity in m/s reached by the rocket during any
            flight phase.
        Flight.maxAcc : float
            Maximum acceleration in m/s^2 reached by the rocket during
            any flight phase.
        Flight.ax : Function
            Rocket's X acceleration as a function of time, in m/s^2.
        Flight.ay : Function
            Rocket's Y acceleration as a function of time, in m/s^2.
        Flight.az : Function
            Rocket's Z acceleration as a function of time, in m/s^2.
        Flight.alp1 : Function
            Rocket's angular acceleration Alpha 1 as a function of time.
            Units of rad/s^2.
        Flight.alp2 : Function
            Rocket's angular acceleration Alpha 2 as a function of time.
            Units of rad/s^2.
        Flight.alp3 : Function
            Rocket's angular acceleration Alpha 3 as a function of time.
            Units of rad/s^2.
        Flight.cpPosition1 : Function
        Flight.cpPosition2 : Function
        Flight.cpPosition3 : Function
        Flight.staticMargin : Function
            Rocket's static margin function of time in calibers.
        Flight.attackAngle : Function
            Rocket's angle of attack during out of rail flight in
            degrees as a function of time.
        Flight.freestreamSpeed : Function
            Freestream speed, in m/s, as a function of time.
        Flight.streamVelX : Function
            Freestream velocity X component, in m/s, as a function of
            time.
        Flight.streamVelY : Function
            Freestream velocity y component, in m/s, as a function of
            time.
        Flight.streamVelZ : Function
            Freestream velocity z component, in m/s, as a function of
            time.
        Flight.R1 : Function
            Resultant force perpendicular to rockets axis due to
            aerodynamic forces as a function of time. Units in N.
        Flight.R2 : Function
            Resultant force perpendicular to rockets axis due to
            aerodynamic forces as a function of time. Units in N.
        Flight.R3 : Function
            Resultant force in rockets axis due to aerodynamic forces
            as a function of time. Units in N. Usually just drag.
        Flight.M1 : Function
            Resultant momentum perpendicular to rockets axis due to
            aerodynamic forces and excentricity as a function of time.
            Units in N*m.
        Flight.M2 : Function
            Resultant momentum perpendicular to rockets axis due to
            aerodynamic forces and excentricity as a function of time.
            Units in N*m.
        Flight.M3 : Function
            Resultant momentum in rockets axis due to aerodynamic
            forces and excentricity as a function of time. Units in N*m.
        Flight.rotationalEnergy : Function
            Rocket's rotational kinetic energy as a function of time.
            Units in J.
        Flight.translationalEnergy : Function
            Rocket's translational kinetic energy as a function of time.
            Units in J.
        Flight.kineticEnergy : Function
            Rocket's total kinetic energy as a function of time.
            Units in J.
        Flight.potentialEnergy : Function
            Rocket's gravitational potential energy as a function of
            time. Units in J.
        Flight.totalEnergy : Function
            Rocket's total mechanical energy as a function of time.
            Units in J.

    """
    def __init__(self, rocket, environment,
                 inclination=80, heading=90,
                 initialSolution=None,
                 terminateOnApogee=False,
                 maxTime=600,
                 maxTimeStep=np.inf, minTimeStep=0,
                 rtol=1e-6, atol=6*[1e-3] + 4*[1e-6] + 3*[1e-3],
                 timeOvershoot=True,
                 verbose=False):
        """Run a trajectory simulation.

        Parameters
        ----------
        rocket : Rocket
            Rocket to simulate. See help(Rocket) for more information.
        environment : Environment
            Environment to run simulation on. See help(Environment) for
            more information.
        inclination : int, float, optional
            Rail inclination angle relative to ground, given in degrees.
            Default is 80.
        heading : int, float, optional
            Heading angle relative to north given in degrees.
            Default is 90, which points in the x direction.
        initialSolution : array, optional
            Initial solution array to be used. Format is
            initialSolution = [self.tInitial,
                                xInit, yInit, zInit,
                                vxInit, vyInit, vzInit,
                                e0Init, e1Init, e2Init, e3Init,
                                w1Init, w2Init, w3Init].
            If None, the initial solution will start with all null values,
            except for the euler parameters which will be calculated based
            on given values of inclination and heading. Default is None.
        terminateOnApogee : boolean, optioanal
            Wheater to terminate simulation when rocket reaches apogee.
            Default is False.
        maxTime : int, float, optional
            Maximum time in which to simulate trajectory in seconds.
            Default is 600.
        maxTimeStep : int, float, optional
            Maximum time step to use during integration in seconds.
            Default is 0.01.
        minTimeStep : int, float, optional
            Minimum time step to use during integration in seconds.
            Default is 0.01.
        rtol : float, optional
            Maximum relative error tolerance to be tolerated in the
            integration scheme. Default is 1e-6.
        atol : float, optional
            Maximum absolute error tolerance to be tolerated in the
            integration scheme. Default is 1e-6.
        timeOvershoot : bool, optional
            If True, decouples ODE time step from parachute trigger functions
            sampling rate. The time steps can overshoot the necessary trigger
            function evaluation points and then interpolation is used to
            calculate them and feed the triggers. Can greatly improve run
            time in some cases. Default is True.
        verbose : bool, optional
            If true, verbose mode is activated. Default is False.

        Returns
        -------
        None
        """
        # Fetch helper classes and functions
        FlightPhases = self.FlightPhases
        TimeNodes = self.TimeNodes
        timeIterator = self.timeIterator
        
        # Save rocket, parachutes, environment, maximum simulation time
        # and termination events
        self.env = environment
        self.rocket = rocket
        self.parachutes = self.rocket.parachutes[:]
        self.inclination = inclination
        self.heading = heading
        self.maxTime = maxTime
        self.maxTimeStep = maxTimeStep
        self.minTimeStep = minTimeStep
        self.rtol = rtol
        self.atol = atol
        self.initialSolution = initialSolution
        self.timeOvershoot = timeOvershoot
        self.terminateOnApogee = terminateOnApogee


        # Flight initialization
        # Initialize solution monitors
        self.outOfRailTime = 0
        self.outOfRailState = 0
        self.outOfRailVelocity = 0
        self.apogeeState = 0
        self.apogeeTime = 0
        self.apogeeX = 0
        self.apogeeY = 0
        self.apogee = 0
        self.xImpact = 0
        self.yImpact = 0
        self.impactVelocity = 0
        self.impactState = 0
        self.parachuteEvents = []
        # Intialize solver monitors
        self.functionEvaluations = []
        self.functionEvaluationsPerTimeStep = []
        self.timeSteps = []
        # Initialize solution state
        self.solution = []
        if self.initialSolution is None:
            # Define launch heading and angle - initial attitude
            launchAngle = (90 - inclination)*(np.pi/180)
            rotAngle = (90 - heading)*(np.pi/180)
            rotAxis = np.array([-np.sin(rotAngle), np.cos(rotAngle), 0])

            # Initialize time and state variables
            self.tInitial = 0
            xInit, yInit, zInit = 0, 0, 0
            vxInit, vyInit, vzInit = 0, 0, 0
            w1Init, w2Init, w3Init = 0, 0, 0
            e0Init = np.cos(launchAngle/2)
            e1Init = np.sin(launchAngle/2) * rotAxis[0]
            e2Init = np.sin(launchAngle/2) * rotAxis[1]
            e3Init = 0
            self.initialSolution = [self.tInitial,
                                    xInit, yInit, zInit,
                                    vxInit, vyInit, vzInit,
                                    e0Init, e1Init, e2Init, e3Init,
                                    w1Init, w2Init, w3Init]
        self.solution.append(self.initialSolution)
        self.t = self.solution[-1][0]
        self.y = self.solution[-1][1:]
        
        # Create knonw flight phases
        self.flightPhases = FlightPhases()
        self.flightPhases.addPhase(self.tInitial, self.uDotRail, clear=False)
        self.flightPhases.addPhase(self.maxTime)

        # Simulate fligh
        for phase_index, phase in timeIterator(self.flightPhases):
            # print('\nCurrent Flight Phase List')
            # print(self.flightPhases)
            # print('\n\tCurrent Flight Phase')
            # print('\tIndex: ', phase_index, ' | Phase: ', phase)
            # Determine maximum time for this flight phase
            phase.timeBound = self.flightPhases[phase_index + 1].t
            
            # Evaluate callbacks
            for callback in phase.callbacks:
                callback(self)

            # Create solver for this flight phase
            self.functionEvaluations.append(0)
            phase.solver = integrate.LSODA(phase.derivative,
                                            t0=phase.t, y0=self.y,
                                            t_bound=phase.timeBound,
                                            min_step=self.minTimeStep,
                                            max_step=self.maxTimeStep,
                                            rtol=self.rtol, atol=self.atol)
            # print('\n\tSolver Initialization Details')
            # print('\tInitial Time: ', phase.t)
            # print('\tInitial State: ', self.y)
            # print('\tTime Bound: ', phase.timeBound)
            # print('\tMin Step: ', self.minTimeStep)
            # print('\tMax Step: ', self.maxTimeStep)
            # print('\tTolerances: ', self.rtol, self.atol)

            # Initialize phase time nodes
            phase.timeNodes = TimeNodes()
            # Add first time node to permanent list
            phase.timeNodes.addNode(phase.t, [], [])
            # Add non-overshootable parachute time nodes
            if self.timeOvershoot is False:
                phase.timeNodes.addParachutes(self.parachutes, phase.t, phase.timeBound)
            # Add lst time node to permanent list
            phase.timeNodes.addNode(phase.timeBound, [], [])
            # Sort time nodes
            phase.timeNodes.sort()
            # Merge equal time nodes
            phase.timeNodes.merge()
            # Clear triggers from first time node if necessary
            if phase.clear:
                phase.timeNodes[0].parachutes = []
                phase.timeNodes[0].callbacks = []

            # print('\n\tPhase Time Nodes')
            # print('\tTime Nodes Length: ', str(len(phase.timeNodes)), ' | Time Nodes Preview: ', phase.timeNodes[0:3])

            # Iterate through time nodes
            for node_index, node in timeIterator(phase.timeNodes):
                # print('\n\t\tCurrent Time Node')
                # print('\t\tIndex: ', node_index, ' | Time Node: ', node)
                # Determine time bound for this time node
                node.timeBound = phase.timeNodes[node_index + 1].t
                phase.solver.t_bound = node.timeBound
                phase.solver._lsoda_solver._integrator.rwork[0] = phase.solver.t_bound
                phase.solver._lsoda_solver._integrator.call_args[4] = phase.solver._lsoda_solver._integrator.rwork
                phase.solver.status = 'running'

                # Feed required parachute and discrete controller triggers
                for callback in node.callbacks:
                    callback(self)

                for parachute in node.parachutes:
                    # Calculate and save pressure signal
                    pressure = self.env.pressure.getValueOpt(self.y[2])
                    parachute.cleanPressureSignal.append([node.t, pressure])
                    # Calculate and save noise
                    noise = parachute.noiseFunction()
                    parachute.noiseSignal.append([node.t, noise])
                    parachute.noisyPressureSignal.append([node.t, pressure + noise])
                    if parachute.trigger(pressure + noise, self.y):
                        # print('\nEVENT DETECTED')
                        # print('Parachute Triggered')
                        # print('Name: ', parachute.name, ' | Lag: ', parachute.lag)
                        # Remove parachute from flight parachutes
                        self.parachutes.remove(parachute)
                        # Create flight phase for time after detection and before inflation
                        self.flightPhases.addPhase(node.t, phase.derivative, clear=True, index=phase_index + 1)
                        # Create flight phase for time after inflation
                        callbacks = [lambda self, parachuteCdS=parachute.CdS: setattr(self, 'parachuteCdS', parachuteCdS)]
                        self.flightPhases.addPhase(node.t + parachute.lag, self.uDotParachute, callbacks, clear=False, index=phase_index + 2)
                        # Prepare to leave loops and start new flight phase
                        phase.timeNodes.flushAfter(node_index)
                        phase.timeNodes.addNode(self.t, [], [])
                        phase.solver.status = 'finished'
                        # Save parachute event
                        self.parachuteEvents.append([self.t, parachute])
                
                # Step through simulation
                while phase.solver.status == 'running':
                    # Step
                    phase.solver.step()
                    # Save step result
                    self.solution += [[phase.solver.t, *phase.solver.y]]
                    # Step step metrics
                    self.functionEvaluationsPerTimeStep.append(phase.solver.nfev - self.functionEvaluations[-1])
                    self.functionEvaluations.append(phase.solver.nfev)
                    self.timeSteps.append(phase.solver.step_size)
                    # Update time and state
                    self.t = phase.solver.t
                    self.y = phase.solver.y
                    if verbose: print('Current Simulation Time: {:3.4f} s'.format(self.t), end='\r')
                    # print('\n\t\t\tCurrent Step Details')
                    # print('\t\t\tIState: ', phase.solver._lsoda_solver._integrator.istate)
                    # print('\t\t\tTime: ', phase.solver.t)
                    # print('\t\t\tAltitude: ', phase.solver.y[2])
                    # print('\t\t\tEvals: ', self.functionEvaluationsPerTimeStep[-1])
                    # Check for out of rail event
                    if self.outOfRailState is 0 and (self.y[0]**2 + self.y[1]**2 + self.y[2]**2 >= self.env.rL**2):
                        # Rocket is out of rail
                        # Check exactly when it went out using root finding
                        # States before and after
                        # t0 -> 0
                        # print('\nEVENT DETECTED')
                        # print('Rocket is Out of Rail!')
                        y0 = sum([self.solution[-2][i]**2 for i in [1, 2, 3]]) - self.env.rL**2
                        yp0 = 2*sum([self.solution[-2][i]*self.solution[-2][i+3] for i in [1, 2, 3]])
                        t1 = self.solution[-1][0] - self.solution[-2][0]
                        y1 = sum([self.solution[-1][i]**2 for i in [1, 2, 3]]) - self.env.rL**2
                        yp1 = 2*sum([self.solution[-1][i]*self.solution[-1][i+3] for i in [1, 2, 3]])
                        # Cubic Hermite interpolation (ax**3 + bx**2 + cx + d)
                        D = float(phase.solver.step_size)
                        d = float(y0)
                        c = float(yp0)
                        b = float((3*y1 - yp1*D - 2*c*D - 3*d)/(D**2))
                        a = float(-(2*y1 - yp1*D - c*D - 2*d)/(D**3))
                        # Find roots
                        d0 = b**2 - 3*a*c
                        d1 = 2*b**3 - 9*a*b*c + 27*d*a**2
                        c1 = ((d1 + (d1**2 - 4*d0**3)**(0.5))/2)**(1/3)
                        t_roots = []
                        for k in [0, 1, 2]:
                            c2 = c1*(-1/2 + 1j*(3**0.5)/2)**k
                            t_roots.append(-(1/(3*a))*(b + c2 + d0/c2))
                        # Find correct root
                        valid_t_root = []
                        for t_root in t_roots:
                            if 0 < t_root.real < t1 and abs(t_root.imag) < 0.001:
                                valid_t_root.append(t_root.real)
                        if len(valid_t_root) > 1:
                            raise ValueError('Multiple roots found when solving for rail exit time.')
                        # Determine final state when going out of rail
                        self.t = valid_t_root[0] + self.solution[-2][0]
                        interpolator = phase.solver.dense_output()
                        self.y = interpolator(self.t)
                        self.solution[-1] = [self.t, *self.y]
                        self.outOfRailTime = self.t
                        self.outOfRailState = self.y
                        self.outOfRailVelocity = (self.y[3]**2 +
                                                  self.y[4]**2 +
                                                  self.y[5]**2)**(0.5)
                        # Create new flight phase
                        self.flightPhases.addPhase(self.t, self.uDot, index=phase_index+1)
                        # Prepare to leave loops and start new flight phase
                        phase.timeNodes.flushAfter(node_index)
                        phase.timeNodes.addNode(self.t, [], [])
                        phase.solver.status = 'finished' 
                    # Check for apogee event
                    if self.apogeeState is 0 and self.y[5] < 0:
                        # print('\nPASSIVE EVENT DETECTED')
                        # print('Rocket Has Reached Apogee!')
                        # Apogee reported
                        # Assume linear vz(t) to detect when vz = 0
                        vz0 = self.solution[-2][6]
                        t0 = self.solution[-2][0]
                        vz1 = self.solution[-1][6]
                        t1 = self.solution[-1][0]
                        t_root = -(t1-t0)*vz0/(vz1-vz0) + t0
                        # Fecth state at t_root
                        interpolator = phase.solver.dense_output()
                        self.apogeeState = interpolator(t_root)
                        # Store apogee data
                        self.apogeeTime = t_root
                        self.apogeeX = self.apogeeState[0]
                        self.apogeeY = self.apogeeState[1]
                        self.apogee = self.apogeeState[2]
                        if self.terminateOnApogee:
                            # print('Terminate on Apogee Activated!')
                            self.t = t_root
                            self.tFinal = self.t
                            self.state = self.apogeeState
                            # Roll back solution
                            self.solution[-1] = [self.t, *self.state]
                            # Set last flight phase
                            self.flightPhases.flushAfter(phase_index)
                            self.flightPhases.addPhase(self.t)
                            # Prepare to leave loops and start new flight phase
                            phase.timeNodes.flushAfter(node_index)
                            phase.timeNodes.addNode(self.t, [], [])
                            phase.solver.status = 'finished' 
                    # Check for impact event
                    if self.y[2] < 0:
                        # print('\nPASSIVE EVENT DETECTED')
                        # print('Rocket Has Reached Ground!')
                        # Impact reported
                        # Check exactly when it went out using root finding
                        # States before and after
                        # t0 -> 0
                        y0 = self.solution[-2][3]
                        yp0 = self.solution[-2][6]
                        t1 = self.solution[-1][0] - self.solution[-2][0]
                        y1 = self.solution[-1][3]
                        yp1 = self.solution[-1][6]
                        # Cubic Hermite interpolation (ax**3 + bx**2 + cx + d)
                        D = float(phase.solver.step_size)
                        d = float(y0)
                        c = float(yp0)
                        b = float((3*y1 - yp1*D - 2*c*D - 3*d)/(D**2))
                        a = float(-(2*y1 - yp1*D - c*D - 2*d)/(D**3))
                        # Find roots
                        d0 = b**2 - 3*a*c
                        d1 = 2*b**3 - 9*a*b*c + 27*d*a**2
                        c1 = ((d1 + (d1**2 - 4*d0**3)**(0.5))/2)**(1/3)
                        t_roots = []
                        for k in [0, 1, 2]:
                            c2 = c1*(-1/2 + 1j*(3**0.5)/2)**k
                            t_roots.append(-(1/(3*a))*(b + c2 + d0/c2))
                        # Find correct root
                        valid_t_root = []
                        for t_root in t_roots:
                            if 0 < t_root.real < t1 and abs(t_root.imag) < 0.001:
                                valid_t_root.append(t_root.real)
                        if len(valid_t_root) > 1:
                            raise ValueError('Multiple roots found when solving for impact time.')
                        # Determine impact state at t_root
                        self.t = valid_t_root[0] + self.solution[-2][0]
                        interpolator = phase.solver.dense_output()
                        self.y = interpolator(self.t)
                        # Roll back solution
                        self.solution[-1] = [self.t, *self.y]
                        # Save impact state
                        self.impactState = self.y
                        self.xImpact = self.impactState[0]
                        self.yImpact = self.impactState[1]
                        self.zImpact = self.impactState[2]
                        self.impactVelocity = self.impactState[5]
                        self.tFinal = self.t
                        # Set last flight phase
                        self.flightPhases.flushAfter(phase_index)
                        self.flightPhases.addPhase(self.t)
                        # Prepare to leave loops and start new flight phase
                        phase.timeNodes.flushAfter(node_index)
                        phase.timeNodes.addNode(self.t, [], [])
                        phase.solver.status = 'finished'  
                    
                    # List and feed overshootable time nodes
                    if self.timeOvershoot:
                        # Initialize phase overshootable time nodes
                        overshootableNodes = TimeNodes()
                        # Add overshootable parachute time nodes
                        overshootableNodes.addParachutes(self.parachutes, self.solution[-2][0], self.t)
                        # Add last time node (always skipped)
                        overshootableNodes.addNode(self.t, [], [])
                        if len(overshootableNodes) > 1:
                            # Sort overshootable time nodes
                            overshootableNodes.sort()
                            # Merge equal overshootable time nodes
                            overshootableNodes.merge()
                            # Clear if necessary
                            if overshootableNodes[0].t == phase.t and phase.clear:
                                overshootableNodes[0].parachutes = []
                                overshootableNodes[0].callbacks = []
                            # print('\n\t\t\t\tOvershootable Time Nodes')
                            # print('\t\t\t\tInterval: ', self.solution[-2][0], self.t)
                            # print('\t\t\t\tOvershootable Nodes Length: ', str(len(overshootableNodes)), ' | Overshootable Nodes: ', overshootableNodes)
                            # Feed overshootable time nodes trigger
                            interpolator = phase.solver.dense_output()
                            for overshootable_index, overshootableNode in timeIterator(overshootableNodes):
                                # print('\n\t\t\t\tCurrent Overshootable Node')
                                # print('\t\t\t\tIndex: ', overshootable_index, ' | Overshootable Node: ', overshootableNode)
                                # Calculate state at node time
                                overshootableNode.y = interpolator(overshootableNode.t)
                                # Calculate and save pressure signal
                                pressure = self.env.pressure.getValueOpt(overshootableNode.y[2])
                                for parachute in overshootableNode.parachutes:
                                    # Save pressure signal
                                    parachute.cleanPressureSignal.append([overshootableNode.t, pressure])
                                    # Calculate and save noise
                                    noise = parachute.noiseFunction()
                                    parachute.noiseSignal.append([overshootableNode.t, noise])
                                    parachute.noisyPressureSignal.append([overshootableNode.t, pressure + noise])
                                    if parachute.trigger(pressure + noise, overshootableNode.y):
                                        # print('\nEVENT DETECTED')
                                        # print('Parachute Triggered')
                                        # print('Name: ', parachute.name, ' | Lag: ', parachute.lag)
                                        # Remove parachute from flight parachutes
                                        self.parachutes.remove(parachute)
                                        # Create flight phase for time after detection and before inflation
                                        self.flightPhases.addPhase(overshootableNode.t, phase.derivative, clear=True, index=phase_index + 1)
                                        # Create flight phase for time after inflation
                                        callbacks = [lambda self, parachuteCdS=parachute.CdS: setattr(self, 'parachuteCdS', parachuteCdS)]
                                        self.flightPhases.addPhase(overshootableNode.t + parachute.lag, self.uDotParachute, callbacks, clear=False, index=phase_index + 2)
                                        # Rollback history
                                        self.t = overshootableNode.t
                                        self.y = overshootableNode.y
                                        self.solution[-1] = [overshootableNode.t, *overshootableNode.y]
                                        # Prepare to leave loops and start new flight phase
                                        overshootableNodes.flushAfter(overshootable_index)
                                        phase.timeNodes.flushAfter(node_index)
                                        phase.timeNodes.addNode(self.t, [], [])
                                        phase.solver.status = 'finished'
                                        # Save parachute event
                                        self.parachuteEvents.append([self.t, parachute])
        
        self.tFinal = self.t
        if verbose: print('Simulation Completed at Time: {:3.4f} s'.format(self.t))

    def uDotRail(self, t, u, verbose=False):
        """Calculates derivative of u state vector with respect to time
        when rocket is flying in 1 DOF motion in the rail.

        Parameters
        ----------
        t : float
            Time in seconds
        u : list
            State vector defined by u = [x, y, z, vx, vy, vz, e0, e1,
            e2, e3, omega1, omega2, omega3].
        verbose : bool, optional
            If True, adds flight data information directly to self
            variables such as self.attackAngle. Default is False.
        
        Return
        ------
        uDot : list
            State vector defined by uDot = [vx, vy, vz, ax, ay, az,
            e0Dot, e1Dot, e2Dot, e3Dot, alpha1, alpha2, alpha3].

        """
        # Retrieve integration data
        x, y, z, vx, vy, vz, e0, e1, e2, e3, omega1, omega2, omega3 = u

        # Retrieve important quantities
        # Mass
        M = self.rocket.totalMass.getValueOpt(t)

        # Get freestrean speed
        freestreamSpeed = ((self.env.windVelocityX.getValueOpt(z) - vx)**2 +
                           (self.env.windVelocityY.getValueOpt(z) - vy)**2 +
                           (vz)**2)**0.5
        freestreamMach = freestreamSpeed/340.40
        dragCoeff = self.rocket.powerOnDrag.getValueOpt(freestreamMach)

        # Calculate Forces
        Thrust = self.rocket.motor.thrust.getValueOpt(t)
        rho = self.env.density.getValueOpt(z)
        R3 = -0.5*rho*(freestreamSpeed**2)*self.rocket.area*(dragCoeff)

        # Calculate Linear acceleration
        a3 = (R3 + Thrust)/M - (e0**2 - e1**2 - e2**2 + e3**2)*self.env.g
        if a3 > 0:
            ax = 2*(e1*e3 + e0*e2) * a3
            ay = 2*(e2*e3 - e0*e1) * a3
            az = (1 - 2*(e1**2 + e2**2)) * a3
        else:
            ax, ay, az = 0, 0, 0

        if verbose:
            windVelocity = np.array([self.env.windVelocityX(z),
                                     self.env.windVelocityY(z), 0])
            rocketVelocity = np.array([vx, vy, vz])
            freestreamVelocity = windVelocity - rocketVelocity
            staticMargin = self.rocket.staticMargin(t)
            self.attackAngle.append([t, 0])
            self.staticMargin.append([t, staticMargin])
            self.freestreamSpeed.append([t, freestreamSpeed])
            self.streamVelX.append([t, freestreamVelocity[0]])
            self.streamVelY.append([t, freestreamVelocity[1]])
            self.streamVelZ.append([t, freestreamVelocity[2]])
            self.R1.append([t, 0])
            self.R2.append([t, 0])
            self.R3.append([t, R3])
            self.M1.append([t, 0])
            self.M2.append([t, 0])
            self.M3.append([t, 0])
            self.ax.append([t, ax])
            self.ay.append([t, ay])
            self.az.append([t, az])

        return [vx, vy, vz, ax, ay, az, 0, 0, 0, 0, 0, 0, 0]
    
    def uDot(self, t, u, verbose=False):
        """Calculates derivative of u state vector with respect to time
        when rocket is flying in 6 DOF motion during ascent out of rail
        and descent without parachute.

        Parameters
        ----------
        t : float
            Time in seconds
        u : list
            State vector defined by u = [x, y, z, vx, vy, vz, e0, e1,
            e2, e3, omega1, omega2, omega3].
        verbose : bool, optional
            If True, adds flight data information directly to self
            variables such as self.attackAngle. Default is False.
        
        Return
        ------
        uDot : list
            State vector defined by uDot = [vx, vy, vz, ax, ay, az,
            e0Dot, e1Dot, e2Dot, e3Dot, alpha1, alpha2, alpha3].

        """
        
        # Retrieve integration data
        x, y, z, vx, vy, vz, e0, e1, e2, e3, omega1, omega2, omega3 = u
        # Determine lift force and moment
        R1, R2 = 0, 0
        M1, M2, M3 = 0, 0, 0
        # Determine current behaviour
        if t < self.rocket.motor.burnOutTime:
            # Motor burning
            # Retrieve important motor quantities
            # Inertias
            Tz = self.rocket.motor.inertiaZ.getValueOpt(t)
            Ti = self.rocket.motor.inertiaI.getValueOpt(t)
            TzDot = self.rocket.motor.inertiaZDot.getValueOpt(t)
            TiDot = self.rocket.motor.inertiaIDot.getValueOpt(t)
            # Mass
            MtDot = self.rocket.motor.massDot.getValueOpt(t)
            Mt = self.rocket.motor.mass.getValueOpt(t)
            # Thrust
            Thrust = self.rocket.motor.thrust.getValueOpt(t)
            # Off center moment
            M1 += self.rocket.thrustExcentricityX*Thrust
            M2 -= self.rocket.thrustExcentricityY*Thrust
        else:
            # Motor stopped
            # Retrieve important motor quantities
            # Inertias
            Tz, Ti, TzDot, TiDot = 0, 0, 0, 0
            # Mass
            MtDot, Mt = 0, 0
            # Thrust
            Thrust = 0

        # Retrieve important quantities
        # Inertias
        Rz = self.rocket.inertiaZ
        Ri = self.rocket.inertiaI
        # Mass
        Mr = self.rocket.mass
        M = Mt + Mr
        mu = (Mt * Mr)/(Mt + Mr)
        # Geometry
        b = -self.rocket.distanceRocketPropellant
        c = -self.rocket.distanceRocketNozzle
        a = b*Mt/M
        rN = self.rocket.motor.nozzleRadius
        # Prepare transformation matrix
        a11 = 1 - 2*(e2**2 + e3**2)
        a12 = 2*(e1*e2 - e0*e3)
        a13 = 2*(e1*e3 + e0*e2)
        a21 = 2*(e1*e2 + e0*e3)
        a22 = 1 - 2*(e1**2 + e3**2)
        a23 = 2*(e2*e3 - e0*e1)
        a31 = 2*(e1*e3 - e0*e2)
        a32 = 2*(e2*e3 + e0*e1)
        a33 = 1 - 2*(e1**2 + e2**2)
        # Transformation matrix: (123) -> (XYZ)
        K = [[a11, a12, a13],
             [a21, a22, a23],
             [a31, a32, a33]]
        # Transformation matrix: (XYZ) -> (123) or K transpose
        Kt = [[a11, a21, a31],
              [a12, a22, a32],
              [a13, a23, a33]]

        # Calculate Forces and Moments
        # Get freestrean speed
        windVelocityX = self.env.windVelocityX.getValueOpt(z)
        windVelocityY = self.env.windVelocityY.getValueOpt(z)
        freestreamSpeed = ((windVelocityX - vx)**2 +
                           (windVelocityY - vy)**2 +
                           (vz)**2)**0.5
        freestreamMach = freestreamSpeed/340.40

        # Determine aerodynamics forces
        # Determine Drag Force
        if t > self.rocket.motor.burnOutTime:
            dragCoeff = self.rocket.powerOnDrag.getValueOpt(freestreamMach)
        else:
            dragCoeff = self.rocket.powerOffDrag.getValueOpt(freestreamMach)
        rho = self.env.density.getValueOpt(z)
        R3 = -0.5*rho*(freestreamSpeed**2)*self.rocket.area*(dragCoeff)
        # Off center moment
        M1 += self.rocket.cpExcentricityY*R3
        M2 -= self.rocket.cpExcentricityX*R3
        # Get rocket velocity in body frame
        vxB = a11*vx + a21*vy + a31*vz
        vyB = a12*vx + a22*vy + a32*vz
        vzB = a13*vx + a23*vy + a33*vz
        # Calculate lift and moment for each component of the rocket
        for aerodynamicSurface in self.rocket.aerodynamicSurfaces:
            compCp = aerodynamicSurface[0][2]
            clalpha = aerodynamicSurface[1]
            # Component absolute velocity in body frame
            compVxB = vxB + compCp * omega2
            compVyB = vyB - compCp * omega1
            compVzB = vzB
            # Wind velocity at component
            compZ = z + compCp
            compWindVx = self.env.windVelocityX.getValueOpt(compZ)
            compWindVy = self.env.windVelocityY.getValueOpt(compZ)
            # Component freestream velocity in body frame
            compWindVxB = a11*compWindVx + a21*compWindVy
            compWindVyB = a12*compWindVx + a22*compWindVy
            compWindVzB = a13*compWindVx + a23*compWindVy
            compStreamVxB = compWindVxB - compVxB
            compStreamVyB = compWindVyB - compVyB
            compStreamVzB = compWindVzB - compVzB
            compStreamSpeed = (compStreamVxB**2 +
                               compStreamVyB**2 +
                               compStreamVzB**2)**0.5
            # Component attack angle and lift force
            compAttackAngle = 0
            compLift, compLiftXB, compLiftYB = 0, 0, 0
            if compStreamVxB**2 + compStreamVyB**2 != 0:
                # Normalize component stream velocity in body frame
                compStreamVzBn = compStreamVzB/compStreamSpeed
                if -1 * compStreamVzBn < 1:
                    compAttackAngle = np.arccos(-compStreamVzBn)
                    # Component lift force magnitude
                    compLift = (0.5*rho*(compStreamSpeed**2)*
                                self.rocket.area*clalpha*compAttackAngle)
                    # Component lift force components
                    liftDirNorm = (compStreamVxB**2+compStreamVyB**2)**0.5
                    compLiftXB = compLift*(compStreamVxB/liftDirNorm)
                    compLiftYB = compLift*(compStreamVyB/liftDirNorm)
                    # Add to total lift force
                    R1 += compLiftXB
                    R2 += compLiftYB
                    # Add to total moment
                    M1 -= (compCp + a) * compLiftYB
                    M2 += (compCp + a) * compLiftXB
        # Calculate derivatives
        # Angular acceleration
        alpha1 = (M1 - (omega2*omega3*(Rz + Tz - Ri - Ti - mu*b**2) +
                  omega1*((TiDot + MtDot*(Mr - 1)*(b/M)**2) -
                          MtDot*((rN/2)**2 + (c - b*mu/Mr)**2))))/(Ri + Ti +
                                                                   mu*b**2)
        alpha2 = (M2 - (omega1*omega3*(Ri + Ti + mu*b**2 - Rz - Tz) +
                  omega2*((TiDot + MtDot*(Mr - 1)*(b/M)**2) -
                          MtDot*((rN/2)**2 + (c - b*mu/Mr)**2))))/(Ri + Ti +
                                                                   mu*b**2)
        alpha3 = (M3 - omega3*(TzDot - MtDot*(rN**2)/2))/(Rz + Tz)
        # Euler parameters derivative
        e0Dot = 0.5*(-omega1*e1 - omega2*e2 - omega3*e3)
        e1Dot = 0.5*(omega1*e0 + omega3*e2 - omega2*e3)
        e2Dot = 0.5*(omega2*e0 - omega3*e1 + omega1*e3)
        e3Dot = 0.5*(omega3*e0 + omega2*e1 - omega1*e2)

        # Linear acceleration
        L = [(R1 - b*Mt*(omega2**2 + omega3**2) - 2*c*MtDot*omega2)/M,
             (R2 + b*Mt*(alpha3 + omega1*omega2) + 2*c*MtDot*omega1)/M,
             (R3 - b*Mt*(alpha2 - omega1*omega3) + Thrust)/M]
        ax, ay, az = np.dot(K, L)
        az -= self.env.g  # Include gravity

        # Create uDot
        uDot = [vx, vy, vz, ax, ay, az, e0Dot, e1Dot, e2Dot, e3Dot,
                alpha1, alpha2, alpha3]

        if verbose:
            # Calculate rocket attackAngle for graphing porpuses
            # Get stream direction in 123 base - from xyz base
            windVelocity = np.array([self.env.windVelocityX(z),
                                     self.env.windVelocityY(z), 0])
            rocketVelocity = np.array([vx, vy, vz])
            freestreamVelocity = windVelocity - rocketVelocity
            streamDirection = freestreamVelocity/freestreamSpeed
            streamDirection = np.dot(Kt, streamDirection)
            attackAngle = (0 if -1 * streamDirection[2] >= 1 else
                           np.arccos(-streamDirection[2]))
            # Correct drag direction
            if attackAngle == np.pi:
                R3 *= -1
            if math.isnan(attackAngle):
                print('Error: NaN at t: ' + str(t))
                attackAngle = 0
            # Calculate trajectory angle
            rocketZVector = np.dot(np.array(K), np.array([0, 0, 1]))
            # XZ plane
            trajectoryAngleXZ = np.arctan2(rocketZVector[0], rocketZVector[2])
            # YZ plane
            trajectoryAngleYZ = np.arctan2(rocketZVector[1], rocketZVector[2])
            # Calculate Static Margin
            d = 2*self.rocket.radius
            R123 = np.dot(Kt, [R1, R2, 0])
            Rsquared = R1**2 + R2**2 if R1**2 + R2**2 != 0 else 0.00001
            cpPosition = np.cross(R123, [M1, M2, M3])/Rsquared
            staticMargin = (abs(cpPosition[2]) - a)/d
            staticMargin = ((M1**2 + M2**2)/Rsquared - a)/d
            staticMargin = self.rocket.staticMargin(t)
            # Store Data
            self.cpPosition1.append([t, cpPosition[0]])
            self.cpPosition2.append([t, cpPosition[1]])
            self.cpPosition3.append([t, cpPosition[2]])
            self.staticMargin.append([t, staticMargin])
            self.attackAngle.append([t, attackAngle*180/np.pi])
            self.trajectoryAngleXZ.append([t, trajectoryAngleXZ*180/np.pi])
            self.trajectoryAngleYZ.append([t, trajectoryAngleYZ*180/np.pi])
            self.freestreamSpeed.append([t, freestreamSpeed])
            self.streamVelX.append([t, freestreamVelocity[0]])
            self.streamVelY.append([t, freestreamVelocity[1]])
            self.streamVelZ.append([t, freestreamVelocity[2]])
            self.R1.append([t, R1])
            self.R2.append([t, R2])
            self.R3.append([t, R3])
            self.M1.append([t, M1])
            self.M2.append([t, M2])
            self.M3.append([t, M3])
            self.ax.append([t, ax])
            self.ay.append([t, ay])
            self.az.append([t, az])
            self.alp1.append([t, alpha1])
            self.alp2.append([t, alpha2])
            self.alp3.append([t, alpha3])

        # Return uDot
        return uDot

    def uDotParachute(self, t, u, verbose=False):
        """Calculates derivative of u state vector with respect to time
        when rocket is flying under parachute. A 3 DOF aproximation is
        used.

        Parameters
        ----------
        t : float
            Time in seconds
        u : list
            State vector defined by u = [x, y, z, vx, vy, vz, e0, e1,
            e2, e3, omega1, omega2, omega3].
        verbose : bool, optional
            If True, adds flight data information directly to self
            variables such as self.attackAngle. Default is False.
        
        Return
        ------
        uDot : list
            State vector defined by uDot = [vx, vy, vz, ax, ay, az,
            e0Dot, e1Dot, e2Dot, e3Dot, alpha1, alpha2, alpha3].

        """
        # Parachute data
        CdS = self.parachuteCdS
        ka = 1
        R = 1.5
        rho = self.env.density.getValueOpt(u[2])
        to = 1.2
        ma = ka*rho*(4/3)*np.pi*R**3
        mp = self.rocket.mass
        eta = 1
        Rdot = (6*R*(1-eta)/(1.2**6))*((1-eta)*t**5 + eta*(to**3)*(t**2))
        Rdot = 0
        # Get relevant state data
        x, y, z, vx, vy, vz, e0, e1, e2, e3, omega1, omega2, omega3 = u
        # Get wind data
        windVelocityX = self.env.windVelocityX.getValueOpt(z)
        windVelocityY = self.env.windVelocityY.getValueOpt(z)
        freestreamSpeed = ((windVelocityX - vx)**2 +
                           (windVelocityY - vy)**2 +
                           (vz)**2)**0.5
        freestreamX = vx - windVelocityX
        freestreamY = vy - windVelocityY
        freestreamZ = vz
        # Determine drag force
        pseudoD = -0.5 * CdS * freestreamSpeed - ka*rho*4*np.pi*(R**2)*Rdot
        Dx = pseudoD * freestreamX
        Dy = pseudoD * freestreamY
        Dz = pseudoD * freestreamZ
        ax = Dx/(mp+ma)
        ay = Dy/(mp+ma)
        az = (Dz - 9.8*mp)/(mp+ma)

        if verbose:
            windVelocity = np.array([self.env.windVelocityX(z),
                                     self.env.windVelocityY(z), 0])
            rocketVelocity = np.array([vx, vy, vz])
            freestreamVelocity = windVelocity - rocketVelocity
            self.freestreamSpeed.append([t, freestreamSpeed])
            self.streamVelX.append([t, freestreamVelocity[0]])
            self.streamVelY.append([t, freestreamVelocity[1]])
            self.streamVelZ.append([t, freestreamVelocity[2]])
            self.R1.append([t, Dx])
            self.R2.append([t, Dy])
            self.R3.append([t, Dz])
            self.ax.append([t, ax])
            self.ay.append([t, ay])
            self.az.append([t, az])

        return [vx, vy, vz, ax, ay, az, 0, 0, 0, 0, 0, 0, 0]

    def postProcess(self):
        """Post-process all Flight information produced during
        simulation. Includes the calculation of maximum values,
        calculation of secundary values such as energy and conversion
        of lists to Function objects to facilitate plotting.

        Parameters
        ----------
        None
        
        Return
        ------
        None
        """
        # Transform solution array into Functions
        sol = np.array(self.solution)
        self.x = Function(sol[:, [0, 1]], 'Time (s)', 'X (m)', 'spline', extrapolation="natural")
        self.y = Function(sol[:, [0, 2]], 'Time (s)', 'Y (m)', 'spline', extrapolation="natural")
        self.z = Function(sol[:, [0, 3]], 'Time (s)', 'Z (m)', 'spline', extrapolation="natural")
        self.vx = Function(sol[:, [0, 4]], 'Time (s)', 'Vx (m/s)', 'spline', extrapolation="natural")
        self.vy = Function(sol[:, [0, 5]], 'Time (s)', 'Vy (m/s)', 'spline', extrapolation="natural")
        self.vz = Function(sol[:, [0, 6]], 'Time (s)', 'Vz (m/s)', 'spline', extrapolation="natural")
        self.e0 = Function(sol[:, [0, 7]], 'Time (s)', 'e0', 'spline', extrapolation="natural")
        self.e1 = Function(sol[:, [0, 8]], 'Time (s)', 'e1', 'spline', extrapolation="natural")
        self.e2 = Function(sol[:, [0, 9]], 'Time (s)', 'e2', 'spline', extrapolation="natural")
        self.e3 = Function(sol[:, [0, 10]], 'Time (s)', 'e3', 'spline', extrapolation="natural")
        self.w1 = Function(sol[:, [0, 11]], 'Time (s)', 'ω1 (rad/s)', 'spline', extrapolation="natural")
        self.w2 = Function(sol[:, [0, 12]], 'Time (s)', 'ω2 (rad/s)', 'spline', extrapolation="natural")
        self.w3 = Function(sol[:, [0, 13]], 'Time (s)', 'ω3 (rad/s)', 'spline', extrapolation="natural")
        
        # Transform parachute sensor feed into functions
        for parachute in self.rocket.parachutes:
            parachute.cleanPressureSignalFunction = Function(parachute.cleanPressureSignal, 'Time (s)', 'Pressure - Without Noise (Pa)', 'linear')
            parachute.noisyPressureSignalFunction = Function(parachute.noisyPressureSignal, 'Time (s)', 'Pressure - With Noise (Pa)', 'linear')
            parachute.noiseSignalFunction = Function(parachute.noiseSignal, 'Time (s)', 'Pressure Noise (Pa)', 'linear')

        # Calculate aerodynamic forces and accelerations
        self.cpPosition1, self.cpPosition2, self.cpPosition3 = [], [], []
        self.staticMargin = []
        self.attackAngle, self.freestreamSpeed = [], []
        self.trajectoryAngleXZ, self.trajectoryAngleYZ = [], []
        self.trajectoryXZ, self.trajectoryYZ, self.trajectoryXY = [], [], []
        self.R1, self.R2, self.R3 = [], [], []
        self.M1, self.M2, self.M3 = [], [], []
        self.ax, self.ay, self.az = [], [], []
        self.alp1, self.alp2, self.alp3 = [], [], []
        self.streamVelX, self.streamVelY, self.streamVelZ = [], [], []
        
        for phase_index, phase in self.timeIterator(self.flightPhases):
            initTime = phase.t
            finalTime = self.flightPhases[phase_index + 1].t
            currentDerivative = phase.derivative
            for callback in phase.callbacks:
                callback(self)
            for step in self.solution:
                if initTime < step[0] <= finalTime:
                    currentDerivative(step[0], step[1:], verbose=True)
 
        self.cpPosition1 = Function(self.cpPosition1, 'Time (s)',
                                    'CP Position in X (m)', 'linear')
        self.cpPosition2 = Function(self.cpPosition2, 'Time (s)',
                                    'CP Position in Y (m)', 'linear')
        self.cpPosition3 = Function(self.cpPosition3, 'Time (s)',
                                    'CP Position in Z (m)', 'linear')
        self.staticMargin = Function(self.staticMargin, 'Time (s)',
                                     'Static Margin (c)', 'linear')
        self.attackAngle = Function(self.attackAngle, 'Time (s)',
                                    'Angle of Attack (Deg)', 'linear')
        self.trajectoryAngleXZ = Function(self.trajectoryAngleXZ, 'Time (s)',
                                          'Trajectory Angle XZ (Deg)', 'linear')
        self.trajectoryAngleYZ = Function(self.trajectoryAngleYZ, 'Time (s)',
                                          'Trajectory Angle YZ (Deg)', 'linear')                                  
        self.freestreamSpeed = Function(self.freestreamSpeed, 'Time (s)',
                                        'Freestream Speed (m/s)', 'linear')
        self.streamVelX = Function(self.streamVelX, 'Time (s)',
                                   'Freestream VelX (m/s)', 'linear')
        self.streamVelY = Function(self.streamVelY, 'Time (s)',
                                   'Freestream VelY (m/s)', 'linear')
        self.streamVelZ = Function(self.streamVelZ, 'Time (s)',
                                   'Freestream VelZ (m/s)', 'linear')
        self.R1 = Function(self.R1, 'Time (s)', 'R1 (N)', 'linear')
        self.R2 = Function(self.R2, 'Time (s)', 'R2 (N)', 'linear')
        self.R3 = Function(self.R3, 'Time (s)', 'R3 (N)', 'linear')
        self.M1 = Function(self.M1, 'Time (s)', 'M1 (Nm)', 'linear')
        self.M2 = Function(self.M2, 'Time (s)', 'M2 (Nm)', 'linear')
        self.M3 = Function(self.M3, 'Time (s)', 'M3 (Nm)', 'linear')
        self.ax = Function(self.ax, 'Time (s)', 'Ax (m/s2)', 'linear')
        self.ay = Function(self.ay, 'Time (s)', 'Ay (m/s2)', 'linear')
        self.az = Function(self.az, 'Time (s)', 'Az (m/s2)', 'linear')
        self.alp1 = Function(self.alp1, 'Time (s)', 'α1 (rad/s2)', 'linear')
        self.alp2 = Function(self.alp2, 'Time (s)', 'α2 (rad/s2)', 'linear')
        self.alp3 = Function(self.alp3, 'Time (s)', 'α3 (rad/s2)', 'linear')
        self.trajectoryXZ = Function(np.array([self.x[:, 1], self.z[:, 1]]).T, 'X (m)', 'Z (m)', 'linear')
        self.trajectoryYZ = Function(np.array([self.y[:, 1], self.z[:, 1]]).T, 'Y (m)', 'Z (m)', 'linear')
        self.trajectoryXY = Function(np.array([self.x[:, 1], self.y[:, 1]]).T, 'X (m)', 'Y (m)', 'linear')

        # Process velocity and acceleration magnitude
        self.v = (self.vx**2 + self.vy**2 + self.vz**2)**0.5
        self.v.setOutputs('Velocity Magnitude (m/s)')
        self.a = (self.ax**2 + self.ay**2 + self.az**2)**0.5
        self.a.setOutputs('Acceleration Magnitude (m/s)')
        
        # Find out of rail and apogee velocity
        self.outOfRailVelocity = (self.vx(self.outOfRailTime)**2 +
                                  self.vy(self.outOfRailTime)**2 +
                                  self.vz(self.outOfRailTime)**2)**(0.5)
        self.apogeeVelocity = (self.vx(self.apogeeTime)**2 +
                               self.vy(self.apogeeTime)**2)**(0.5)
        
        # Find out maximum velocity and acceleration
        self.maxVel = np.amax(self.v.source[:, 1])
        self.maxAcc = np.amax(self.a.source[:, 1])
        
        # Calculate Energies
        # Retrieve variables
        # Geometry
        b = -self.rocket.distanceRocketPropellant
        # Mass
        totalMass = self.rocket.totalMass
        mu = self.rocket.reducedMass
        # Inertias
        Rz = self.rocket.inertiaZ
        Ri = self.rocket.inertiaI
        Tz = self.rocket.motor.inertiaZ
        Ti = self.rocket.motor.inertiaI
        I1, I2, I3 = (Ri + Ti + mu*b**2), (Ri + Ti + mu*b**2), (Rz + Tz)
        # Velocities
        vx, vy, vz = self.vx, self.vy, self.vz
        w1, w2, w3 = self.w1, self.w2, self.w3
        # Calculate Energy Quantities
        # Kinetic Energy
        self.rotationalEnergy = 0.5*(I1*w1**2 + I2*w2**2 + I3*w3**2)
        self.rotationalEnergy.setOutputs('Rotational Kinetic Energy (J)')
        self.translationalEnergy = 0.5*totalMass*(vx**2 + vy**2 + vz**2)
        self.translationalEnergy.setOutputs('Translational Kinetic Energy (J)')
        self.kineticEnergy = self.rotationalEnergy + self.translationalEnergy
        self.kineticEnergy.setOutputs('Kinetic Energy (J)')
        # Potential Energy
        self.potentialEnergy = self.rocket.totalMass*self.env.g*self.z
        self.potentialEnergy.setInputs('Time (s)')
        # Total Mechanical Energy
        self.totalEnergy = self.kineticEnergy + self.potentialEnergy
        self.totalEnergy.setOutputs('Total Mechanical Energy (J)')

        return None

    def info(self):
        """Prints out a summary of the data and graphs available about
        the Flight.

        Parameters
        ----------
        None
        
        Return
        ------
        None
        """
        # Post-process results
        self.postProcess()

        # Print off rail conditions
        print('\nOff Rail Conditions')
        print('Rail Departure Time: ' +
              "{:.3f}".format(self.outOfRailTime) + ' s')
        print('Rail Departure Velocity: ' +
              "{:.3f}".format(self.outOfRailVelocity) + ' m/s')

        # Print apogee conditions
        print('\nApogee')
        print('Altitude: ' + "{:.3f}".format(self.apogee) + ' m')
        print('Velocity: ' + "{:.3f}".format(self.apogeeVelocity) + ' m/s')
        print('Time: ' + "{:.3f}".format(self.apogeeTime) + ' s')
        print('Freestream Speed: ' +
              "{:.3f}".format(self.freestreamSpeed(self.apogeeTime)) + ' m/s')

        # Print events registered
        print('\nEvents')
        if len(self.parachuteEvents) == 0:
            print('No Parachute Events Were Triggered.')
        for event in self.parachuteEvents:
            triggerTime = event[0]
            parachute = event[1]
            openTime = triggerTime + parachute.lag
            velocity = self.freestreamSpeed(openTime)
            altitude = self.z(openTime)
            name = parachute.name.title()
            print(name + ' Ejection Triggered at: ' + "{:.3f}".format(triggerTime) + ' s')
            print(name + ' Parachute Inflated at: ' + "{:.3f}".format(openTime) + ' s')
            print(name + ' Parachute Inflated with Freestream Speed of: ' + "{:.3f}".format(velocity) + ' m/s')
            print(name + ' Parachute Inflated at Height of: ' + "{:.3f}".format(altitude) + ' m')

        # Print impact conditions
        if not (self.impactState is 0):
            print('\nImpact')
            print('X Impact: ' + "{:.3f}".format(self.xImpact) + ' m')
            print('Y Impact: ' + "{:.3f}".format(self.yImpact) + ' m')
            print('Time of Impact: ' + "{:.3f}".format(self.tFinal) + ' s')
            print('Velocity at Impact: ' + "{:.3f}".format(self.impactVelocity) +
                ' m/s')
        elif self.terminateOnApogee is False:   
            print('\nEnd of Simulation:')
            print('Time: ' + "{:.3f}".format(self.solution[-1][0]) + ' s')
            print('Altitude: ' + "{:.3f}".format(self.solution[-1][3]) + ' m')
        # Print maximum velocity and maximum acceleration
        print('\nMaximum Velocity and Acceleration')
        print('Velocity: ' + "{:.3f}".format(self.maxVel) + ' m/s')
        print('Acceleration: ' + "{:.3f}".format(self.maxAcc) + ' m/s2')

        print('\nTrajectory Plots')
        fig = plt.figure()
        ax = fig.gca(projection='3d')
        ax.set_xlabel('X (m)')
        ax.set_ylabel('Y (m)')
        ax.set_zlabel('Z (m)')
        ax.plot(self.x.source[:, 1], self.y.source[:, 1], self.z.source[:, 1])
        plt.show()
        return None
    
    def allInfo(self):
        """Prints out all data and graphs available about the Flight.

        Parameters
        ----------
        None
        
        Return
        ------
        None
        """
        # Post-process results
        self.postProcess()
        # Print environment details
        print('Environment Details')
        print('Gravitational Acceleration: ' + str(self.env.g) + ' m/s2')
        print('Rail Length: ' + str(self.env.rL) + ' m')

        # Print initial conditions
        print('\nInitial Conditions')
        print('Position - x: ' + str(self.x(0)) + ' m')
        print('Position - y: ' + str(self.y(0)) + ' m')
        print('Position - z: ' + str(self.z(0)) + ' m')
        print('Velocity - Vx: ' + str(self.vx(0)) + ' m/s')
        print('Velocity - Vy: ' + str(self.vy(0)) + ' m/s')
        print('Velocity - Vz: ' + str(self.vz(0)) + ' m/s')
        print('Orientation - e0: ' + str(self.e0(0)))
        print('Orientation - e1: ' + str(self.e1(0)))
        print('Orientation - e2: ' + str(self.e2(0)))
        print('Orientation - e3: ' + str(self.e3(0)))
        print('Angular Velocity - ω1: ' + str(self.w1(0)) + ' rad/s')
        print('Angular Velocity - ω2: ' + str(self.w2(0)) + ' rad/s')
        print('Angular Velocity - ω3: ' + str(self.w3(0)) + ' rad/s')

        # Print off rail conditions
        print('\nOff Rail Conditions')
        print('Rail Departure Time: ' +
              "{:.3f}".format(self.outOfRailTime) + ' s')
        print('Rail Departure Velocity: ' +
              "{:.3f}".format(self.outOfRailVelocity) + ' m/s')
        
        # Print apogee conditions
        print('\nApogee')
        print('Altitude: ' + "{:.3f}".format(self.apogee) + ' m')
        print('Velocity: ' + "{:.3f}".format(self.apogeeVelocity) + ' m/s')
        print('Time: ' + "{:.3f}".format(self.apogeeTime) + ' s')
        print('Freestream Speed: ' +
              "{:.3f}".format(self.freestreamSpeed(self.apogeeTime)) + ' m/s')
        
        # Print events registered
        print('\nEvents')
        if len(self.parachuteEvents) == 0:
            print('No Parachute Events Were Triggered.')
        for event in self.parachuteEvents:
            triggerTime = event[0]
            parachute = event[1]
            openTime = triggerTime + parachute.lag
            velocity = self.freestreamSpeed(openTime)
            altitude = self.z(openTime)
            name = parachute.name.title()
            print(name + ' Ejection Triggered at: ' + "{:.3f}".format(triggerTime) + ' s')
            print(name + ' Parachute Inflated at: ' + "{:.3f}".format(openTime) + ' s')
            print(name + ' Parachute Inflated with Freestream Speed of: ' + "{:.3f}".format(velocity) + ' m/s')
            print(name + ' Parachute Inflated at Height of: ' + "{:.3f}".format(altitude) + ' m')

        # Print impact conditions
        if not (self.impactState is 0):
            print('\nImpact')
            print('X Impact: ' + "{:.3f}".format(self.xImpact) + ' m')
            print('Y Impact: ' + "{:.3f}".format(self.yImpact) + ' m')
            print('Time of Impact: ' + "{:.3f}".format(self.tFinal) + ' s')
            print('Velocity at Impact: ' + "{:.3f}".format(self.impactVelocity) +
                ' m/s')
        elif self.terminateOnApogee is False:
            print('\nEnd of Simulation:')
            print('Time: ' + "{:.3f}".format(self.solution[-1][0]) + ' s')
            print('Altitude: ' + "{:.3f}".format(self.solution[-1][3]) + ' m')

        # Print maximum velocity and maximum acceleration
        print('\nMaximum Velocity and Acceleration')
        print('Velocity: ' + "{:.3f}".format(self.maxVel) + ' m/s')
        print('Acceleration: ' + "{:.3f}".format(self.maxAcc) + ' m/s2')

        # All plots
        print('\nTrajectory Plots')
        fig = plt.figure()
        ax = fig.gca(projection='3d')
        ax.set_xlabel('X (m)')
        ax.set_ylabel('Y (m)')
        ax.set_zlabel('Z (m)')
        ax.plot(self.x.source[:, 1], self.y.source[:, 1], self.z.source[:, 1])
        plt.show()
        self.x()
        self.y()
        self.z()
        print('\nVelocity Plots')
        self.vx()
        self.vy()
        self.vz()
        print('\nAcceleration Plots')
        self.ax()
        self.ay()
        self.az()
        print('\nAttitude Plots')
        self.e0()
        self.e1()
        self.e2()
        self.e3()
        print('\nAngular Velocity Plots')
        self.w1()
        self.w2()
        self.w3()
        print('\nAngular Acceleration Plots')
        self.alp1()
        self.alp2()
        self.alp3()
        print('\nEnergy Plots')
        self.rotationalEnergy()
        self.translationalEnergy()
        self.kineticEnergy()
        self.potentialEnergy()
        self.totalEnergy()
        print('\nAerodynamic Forces')
        self.attackAngle()
        self.freestreamSpeed()
        self.R1()
        self.R2()
        self.R3()
        self.M1()
        self.M2()
        self.M3()
        print('\nParachute Trigger Pressure Signals')
        for parachute in self.rocket.parachutes:
            print('Parachute: ', parachute.name)
            parachute.noiseSignalFunction()
            parachute.noisyPressureSignalFunction()
            parachute.cleanPressureSignalFunction()

        return None

    def animate(self, start=0, stop=None, fps=12, speed=4,
                elev=None, azim=None):
        """Plays an animation the flight. Not implemented yet. Only
        kinda works outside notebook.
        """
        # Set up stopping time
        stop = self.tFinal if stop is None else stop
        # Speed = 4 makes it almost real time - matplotlib is way to slow
        # Set up graph
        fig = plt.figure(figsize=(18, 15))
        axes = fig.gca(projection='3d')
        # Initialize time
        timeRange = np.linspace(start, stop, fps * (stop - start))
        # Initialize first frame
        axes.set_title('Trajectory and Velocity Animation')
        axes.set_xlabel('X (m)')
        axes.set_ylabel('Y (m)')
        axes.set_zlabel('Z (m)')
        axes.view_init(elev, azim)
        R = axes.quiver(0, 0, 0, 0, 0, 0, color='r', label='Rocket')
        V = axes.quiver(0, 0, 0, 0, 0, 0, color='g', label='Velocity')
        W = axes.quiver(0, 0, 0, 0, 0, 0, color='b', label='Wind')
        S = axes.quiver(0, 0, 0, 0, 0, 0, color='black', label='Freestream')
        axes.legend()
        # Animate
        for t in timeRange:
            R.remove()
            V.remove()
            W.remove()
            S.remove()
            # Calculate rocket position
            Rx, Ry, Rz = self.x(t), self.y(t), self.z(t)
            Ru = 1*(2*(self.e1(t)*self.e3(t) + self.e0(t)*self.e2(t)))
            Rv = 1*(2*(self.e2(t)*self.e3(t) - self.e0(t)*self.e1(t)))
            Rw = 1*(1 - 2*(self.e1(t)**2 + self.e2(t)**2))
            # Caclulate rocket Mach number
            Vx = self.vx(t)/340.40
            Vy = self.vy(t)/340.40
            Vz = self.vz(t)/340.40
            # Caculate wind Mach Number
            z = self.z(t)
            Wx = self.env.windVelocityX(z)/20
            Wy = self.env.windVelocityY(z)/20
            # Calculate freestream Mach Number
            Sx = self.streamVelX(t)/340.40
            Sy = self.streamVelY(t)/340.40
            Sz = self.streamVelZ(t)/340.40
            # Plot Quivers
            R = axes.quiver(Rx, Ry, Rz, Ru, Rv, Rw, color='r')
            V = axes.quiver(Rx, Ry, Rz, -Vx, -Vy, -Vz, color='g')
            W = axes.quiver(Rx - Vx, Ry - Vy, Rz - Vz, Wx, Wy, 0, color='b')
            S = axes.quiver(Rx, Ry, Rz, Sx, Sy, Sz, color='black')
            # Adjust axis
            axes.set_xlim(Rx - 1, Rx + 1)
            axes.set_ylim(Ry - 1, Ry + 1)
            axes.set_zlim(Rz - 1, Rz + 1)
            # plt.pause(1/(fps*speed))
            try:
                plt.pause(1/(fps*speed))
            except:
                time.sleep(1/(fps*speed))

    def timeIterator(self, nodeList):
        i = 0
        while i < len(nodeList) - 1:
            yield i, nodeList[i]
            i += 1

    class FlightPhases:
        def __init__(self, init_list=[]):
            self.list = init_list[:]
        
        def __getitem__(self, index):
            return self.list[index]

        def __len__(self):
            return len(self.list)

        def __repr__(self):
            return str(self.list)

        def add(self, flightPhase, index=None):
            # Handle first phase
            if len(self.list) == 0:
                self.list.append(flightPhase)
            # Handle appending to last position
            elif index is None:
                # Check if new flight phase respects time
                previousPhase = self.list[-1]
                if flightPhase.t > previousPhase.t:
                    # All good! Add phase.
                    self.list.append(flightPhase)
                elif flightPhase.t == previousPhase.t:
                    print('WARNING: Trying to add a flight phase starting together with the one preceding it.')
                    print('This may be caused by more than when parachute being triggered simultaneously.')
                    flightPhase.t += 1e-7
                    self.add(flightPhase)
                elif flightPhase.t < previousPhase.t:
                    print('WARNING: Trying to add a flight phase starting before the one preceding it.')
                    print('This may be caused by more than when parachute being triggered simultaneously.')
                    self.add(flightPhase, -2)
            # Handle inserting into intermediary position
            else:
                # Check if new flight phase respects time
                nextPhase = self.list[index]
                previousPhase = self.list[index-1]
                if previousPhase.t < flightPhase.t < nextPhase.t:
                    # All good! Add phase.
                    self.list.insert(index, flightPhase)
                elif flightPhase.t < previousPhase.t:
                    print('WARNING: Trying to add a flight phase starting before the one preceding it.')
                    print('This may be caused by more than when parachute being triggered simultaneously.')
                    self.add(flightPhase, index - 1)
                elif flightPhase.t == previousPhase.t:
                    print('WARNING: Trying to add a flight phase starting together with the one preceding it.')
                    print('This may be caused by more than when parachute being triggered simultaneously.')
                    flightPhase.t += 1e-7
                    self.add(flightPhase, index)
                elif flightPhase.t == nextPhase.t:
                    print('WARNING: Trying to add a flight phase starting together with the one proceding it.')
                    print('This may be caused by more than when parachute being triggered simultaneously.')
                    flightPhase.t += 1e-7
                    self.add(flightPhase, index + 1)
                elif flightPhase.t > nextPhase.t:
                    print('WARNING: Trying to add a flight phase starting after the one proceding it.')
                    print('This may be caused by more than when parachute being triggered simultaneously.')
                    self.add(flightPhase, index + 1)

        def addPhase(self, t, derivatives=None, callback=[], clear=True, index=None):
            self.add(self.FlightPhase(t, derivatives, callback, clear), index)

        def flushAfter(self, index):
            del self.list[index+1:]
        
        class FlightPhase:
            def __init__(self, t, derivative=None, callbacks=[], clear=True):
                self.t = t
                self.derivative = derivative
                self.callbacks = callbacks[:]
                self.clear = clear

            def __repr__(self):
                if self.derivative is None:
                    return '{Initial Time: ' + str(self.t) + ' | Derivative: None}'
                return '{Initial Time: ' + str(self.t) + ' | Derivative: ' + self.derivative.__name__ + '}'

    class TimeNodes:
        def __init__(self, init_list=[]):
            self.list = init_list[:]
        
        def __getitem__(self, index):
            return self.list[index]
        
        def __len__(self):
            return len(self.list)
        
        def __repr__(self):
            return str(self.list)

        def add(self, timeNode):
            self.list.append(timeNode)
        
        def addNode(self, t, parachutes, callbacks):
            self.list.append(self.TimeNode(t, parachutes, callbacks))

        def addParachutes(self, parachutes, t_init, t_end):
            # Iterate over parachutes
            for parachute in parachutes:
                # Calculate start of sampling time nodes
                pcDt = 1/parachute.samplingRate
                parachute_node_list = [self.TimeNode(i*pcDt, [parachute], []) for i in range(math.ceil(t_init/pcDt), math.floor(t_end/pcDt) + 1)]
                self.list += parachute_node_list
            
        def sort(self):
            self.list.sort(key=(lambda node: node.t))
        
        def merge(self):
            # Initialize temporary list
            self.tmp_list = [self.list[0]]
            self.copy_list = self.list[1:]
            # Iterate through all other time nodes
            for node in self.copy_list:
                # If there is already another node with similar time: merge
                if abs(node.t - self.tmp_list[-1].t) < 1e-7:
                    self.tmp_list[-1].parachutes += node.parachutes
                    self.tmp_list[-1].callbacks += node.callbacks
                # Add new node to tmp list if there is none with the same time
                else:
                    self.tmp_list.append(node)
            # Save tmp list to permanent
            self.list = self.tmp_list

        def flushAfter(self, index):
            del self.list[index+1:]

        class TimeNode:
            def __init__(self, t, parachutes, callbacks):
                self.t = t
                self.parachutes = parachutes
                self.callbacks = callbacks

            def __repr__(self):
                return '{Initial Time: ' + str(self.t) + ' | Parachutes: ' + str(len(self.parachutes)) + '}'


if __name__ == '__main__':
    
    def drogueTrigger(p, y):
        # return False
        return True if y[5] < 0 else False

    def mainTrigger(p, y):
        # return False
        return True if y[5] < 0 and y[2] < 500 else False

    # Prepare Environment
    Env = Environment(railLength=5.2,
                  gravity=9.8,
                  windData="data/weather/SpacePort.nc",
                  location=(32.990254, -106.974998),
                  date=(2016, 6, 20, 18))

    # Prepare Motor
    Pro75M1670 = Motor(thrustSource="data/motors/Cesaroni_M1670.eng",
                   burnOut=3.9,
                   grainNumber=5,
                   grainSeparation=5/1000,
                   grainDensity=1815,
                   grainOuterRadius=33/1000,
                   grainInitialInnerRadius=15/1000,
                   grainInitialHeight=120/1000,
                   nozzleRadius=33/1000,
                   throatRadius=11/1000,
                   interpolationMethod='linear')

    # Prepare Rocket
    Calisto = Rocket(motor=Pro75M1670,
                         radius=127/2000,
                         mass=19,
                         inertiaI=6.60,
                         inertiaZ=0.0351,
                         distanceRocketNozzle=-1.255,
                         distanceRocketPropellant=-0.85704,
                         powerOffDrag='data/calisto/powerOffDragCurve.csv',
                         powerOnDrag='data/calisto/powerOnDragCurve.csv')
    Nose = Calisto.addNose(length=0.55829, kind="vonKarman", distanceToCM=0.71971)
    FinSet = Calisto.addFins(4, span=0.1, rootChord=0.120, tipChord=0.040, distanceToCM=-1.04956)
    Tail = Calisto.addTail(topRadius=0.0635, bottomRadius=0.0435, length=0.060, distanceToCM=-1.194656)
    Drogue = Calisto.addParachute('Drogue',
                            CdS=1.0,
                            trigger=drogueTrigger, 
                            samplingRate=100,
                            lag=1.5,
                            noise=(0, 0.83, 0.5))

    Main = Calisto.addParachute('Main',
                            CdS=10.0,
                            trigger=mainTrigger, 
                            samplingRate=100,
                            lag=1.5,
                            noise=(0, 0.83, 0.5))
    
    # Simulate Flight until Apogee
    TestFlight = Flight(rocket=Calisto, environment=Env, inclination=85, heading=0)

    TestFlight.postProcess()

    TestFlight = Flight(rocket=Calisto, environment=Env, inclination=85, heading=0)

    Main.noiseSignal()
           
