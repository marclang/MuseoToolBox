#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# ___  ___                       _____           _______           
# |  \/  |                      |_   _|         | | ___ \          
# | .  . |_   _ ___  ___  ___     | | ___   ___ | | |_/ / _____  __
# | |\/| | | | / __|/ _ \/ _ \    | |/ _ \ / _ \| | ___ \/ _ \ \/ /
# | |  | | |_| \__ \  __/ (_) |   | | (_) | (_) | | |_/ / (_) >  < 
# \_|  |_/\__,_|___/\___|\___/    \_/\___/ \___/|_\____/ \___/_/\_\                                                                                                        
#                                             
# @author:  Nicolas Karasiak
# @site:    www.karasiak.net
# @git:     www.github.com/lennepkade/MuseoToolBox
# =============================================================================
from __future__ import absolute_import, print_function
import gdal
import numpy as np
import os
import tempfile
from MuseoToolBox.tools import progressBar,pushFeedback

def convertGdalAndNumpyDataType(gdalDT=None,numpyDT=None):
    """
    Return the datatype from gdal to numpy or from numpy to gdal.
    
    Parameters
    ----------
        gdalDT : int
            gdal datatype from src_dataset.GetRasterBand(1).DataType
        numpyDT : str
            str from array.dtype.name
    """
    from osgeo import gdal_array
    
    NP2GDAL_CONVERSION = {
      "uint8": 1,
      "int8": 1,
      "uint16": 2,
      "int16": 3,
      "uint32": 4,
      "int32": 5,
      "float32": 6,
      "float64": 7,
      "complex64": 10,
      "complex128": 11,
    }
    
    if numpyDT is None:
        return gdal_array.GDALTypeCodeToNumericTypeCode(gdalDT)
    else:
        return NP2GDAL_CONVERSION[numpyDT]
def convertGdalDataTypeToOTB(gdalDT):
    """
    Convert Gdal DataType to OTB str format.
    
    Parameters
    ----------
    gdalDT : int
        gdal Datatype (integer value)
    
    Output
    ----------
    str format of OTB datatype
        availableCode = uint8/uint16/int16/uint32/int32/float/double
    """
    code = ['uint8','uint16','int16','uint32','int32','float','double']
    
    return code[gdalDT]



def getSamplesFromROI(inRaster,inVector,*fields,**kwargs):
    """
    Get the set of pixels given the thematic map. Both map should be of same size. Data is read per block.
        Input:
            raster_name: str.
                the name of the raster file, could be any file that GDAL can open
            roi_name: str.
                the name of the thematic image: each pixel whose values is greater than 0 is returned
            *fields : str.
                Each field to extract label/value from.
            **kwargs:
                Only two keyword args are accepted:
                    getCoords : bool.
                        If getCoords, will return coords for each point.
                    onlyCoords : bool.
                        If true, with only return coords, no X,Y...
        Output:
            X: the sample matrix. A nXd matrix, where n is the number of referenced pixels and d is the number of variables. Each 
                line of the matrix is a pixel.
            Y: the label of the pixel
    Written by Mathieu Fauvel, updated by Nicolas Karasiak.
    """ 
    ## Open Raster
    raster = gdal.Open(inRaster,gdal.GA_ReadOnly)
    if raster is None:
        print('Impossible to open '+inRaster)
        #exit()

    ## Convert vector to raster

    nFields = len(fields)
    rois = []
    temps = []
    for field in fields:
        pushFeedback('Extra field {} has been found'.format(field))
        rstField = tempfile.mktemp('_roi.tif')
        rstField = rasterize(inRaster,inVector,field,rstField)
        roiField = gdal.Open(rstField,gdal.GA_ReadOnly)
        if roiField is None:
            raise Exception('A problem occured when rasterizing {} with field {}'.format(inVector,field))
        if (raster.RasterXSize != roiField.RasterXSize) or (raster.RasterYSize != roiField.RasterYSize):
            raise Exception('Raster and vector do not cover the same extent.')

        rois.append(roiField)
        temps.append(rstField)
    
    ## generate kwargs value
    if 'getCoords' in kwargs:
        getCoords = kwargs['getCoords'] 
    else:
        getCoords = False
    if 'onlyCoords' in kwargs:
        onlyCoords = kwargs['onlyCoords']
    else:
        onlyCoords = False
    
    ## Get block size
    band = raster.GetRasterBand(1)
    block_sizes = band.GetBlockSize()
    x_block_size = block_sizes[0]
    y_block_size = block_sizes[1]
    gdalDT = band.DataType
    del band
    
    ## Get the number of variables and the size of the images
    d  = raster.RasterCount
    nc = raster.RasterXSize
    nl = raster.RasterYSize
    
    ulx, xres, xskew, uly, yskew, yres  = raster.GetGeoTransform()
    
    if getCoords is True or onlyCoords is True:
        coords = np.array([],dtype=np.uint16).reshape(0,2)
            

    ## Read block data
    X = np.array([],dtype=convertGdalDataTypeToOTB(gdalDT)).reshape(0,d)
    #Y = np.array([],dtype=np.int16).reshape(0,1)
    F = np.array([],dtype=np.int16).reshape(0,nFields) # now support multiple fields    
    
    # for progress bar 
    total = nl*y_block_size
    pb = progressBar(total,message='Reading raster values... ')
    
    for i in range(0,nl,y_block_size):

        if i + y_block_size < nl: # Check for size consistency in Y
            lines = y_block_size
        else:
            lines = nl - i
        for j in range(0,nc,x_block_size): # Check for size consistency in X
            if j + x_block_size < nc:
                cols = x_block_size
            else:
                cols = nc - j

            #for progressbar
            currentPosition = int(i+j+1)
            pb.addPosition(currentPosition)
            # Load the reference data
            
            ROI = rois[0].GetRasterBand(1).ReadAsArray(j, i, cols, lines)

            t = np.nonzero(ROI)
            
            if t[0].size > 0:                
                if getCoords or onlyCoords :                  
                    coordsTp = np.empty((t[0].shape[0],2))
                    
                    coordsTp[:,0] = t[1]+j
                    coordsTp[:,1] = t[0]+i

                    coords = np.concatenate((coords,coordsTp))

                # Load the Variables
                if not onlyCoords:
                    # extract values from each field
                    Ftemp = np.empty((t[0].shape[0],nFields),dtype=np.int16)
                    for idx,roiTemp in enumerate(rois):
                        roiField = roiTemp.GetRasterBand(1).ReadAsArray(j, i, cols, lines)
                        Ftemp[:,idx] = roiField[t]
                    F = np.concatenate((F,Ftemp))
                    
                    # extract raster values (X)
                    Xtp = np.empty((t[0].shape[0],d))
                    for k in range(d):
                        band = raster.GetRasterBand(k+1).ReadAsArray(j, i, cols, lines)
                        Xtp[:,k] = band[t]
                    try:
                        X = np.concatenate((X,Xtp))
                    except MemoryError:
                        raise MemoryError('Impossible to allocate memory: ROI too big')
    
    # Clean/Close variables
    # del Xtp,band    
    roi = None # Close the roi file
    raster = None # Close the raster file
   
    # remove temp raster
    for roi in temps:
        os.remove(roi)
        
    # generate output
    toReturn = [X]+[F[:,f].reshape(-1,1) for f in range(nFields)]
    
    if onlyCoords:
        return coords
    if not getCoords :
        return toReturn
    else:
        toReturn.append(coords)
        return toReturn

def rasterize(data,vectorSrc,field,outFile,gdt=gdal.GDT_Int16):
    dataSrc = gdal.Open(data)
    import ogr
    shp = ogr.Open(vectorSrc)

    lyr = shp.GetLayer()

    driver = gdal.GetDriverByName('GTiff')
    dst_ds = driver.Create(outFile,dataSrc.RasterXSize,dataSrc.RasterYSize,1,gdt)
    dst_ds.SetGeoTransform(dataSrc.GetGeoTransform())
    dst_ds.SetProjection(dataSrc.GetProjection())
    if field is None:
        gdal.RasterizeLayer(dst_ds, [1], lyr, None)
    else:
        OPTIONS = ['ATTRIBUTE='+field]
        gdal.RasterizeLayer(dst_ds, [1], lyr, None,options=OPTIONS)
    
    data,dst_ds,shp,lyr=None,None,None,None
    return outFile


  
class rasterMath:
    """
    Read a raster per block, and perform one or many functions to one or many raster outputs.
    
    - If you want to add an output, just use addOutput() function and select raster path, number of bands and datatype.
    - If you want a sample of your data, just call getRandomBlock().
    
    Parameters
    ----------
    inRaster : str
        Gdal supported raster
    outRaster : str
        Path to raster to save (tif file)
    inMaskRaster : str, default False.
        Path to mask raster (masked values are 0). If not, please change self.maskNoData to your value.
    outNBand : int, default 1
        Number of bands of the first output.
    outGdalGDT : int, default 1.
        Gdal DataType of the first output.
    outNoData : int, default False.
        If False, will set the same value as the input raster nodata.
    parallel : int, default False.
        Number of cores to be used if not False.
        
    Output
    ----------
        As many raster (geoTiff) as output defined by the user.
    
    """   
    
    def __init__(self,inRaster,inMaskRaster=False):
        
        # Need to work of parallelize
        ## Not working for the moment
        parallel = False
        self.parallel = parallel
        
        # Load raster
        self.openRaster = gdal.Open(inRaster,gdal.GA_ReadOnly)
        if self.openRaster is None:
            raise ReferenceError('Impossible to open '+inRaster)
            
        self.nb  = self.openRaster.RasterCount
        self.nc = self.openRaster.RasterXSize
        self.nl = self.openRaster.RasterYSize
        
        
        ## Get the geoinformation
        self.GeoTransform = self.openRaster.GetGeoTransform()
        self.Projection = self.openRaster.GetProjection()
    
        ## Get block size
        band = self.openRaster.GetRasterBand(1)
        block_sizes = band.GetBlockSize()
        self.x_block_size = block_sizes[0]
        self.y_block_size = block_sizes[1]
        self.total = self.nl #/self.y_block_size
        
        self.pb = progressBar(self.total-1,message='rasterMath... ')
        self.nodata = band.GetNoDataValue()
        
        if self.nodata is None:
            self.nodata = -9999
        
        del band
    
        # Load inMask if given
        self.mask = inMaskRaster
        if self.mask:
            self.maskNoData = 0
            self.openMask = gdal.Open(inMaskRaster)
            
        ## Initialize the output
        self.functions = []        
        self.outputs = []
        #out = dst_ds.GetRasterBand(1)
        self.lastProgress = 0
        self.outputNoData = []
        
    def addFunction(self,function,outRaster,outNBand,outGdalGDT=False,outNoData=False):
        self.driver = gdal.GetDriverByName('GTiff')
        if outGdalGDT is False:
            dtypeName = function(self.getRandomBlock()).dtype.name
            outGdalGDT = convertGdalAndNumpyDataType(numpyDT = dtypeName)
            pushFeedback('Using datatype from numpy table : '+str(dtypeName))
        self.__addOutput__(outRaster,outNBand,outGdalGDT)
        self.functions.append(function)        
        self.outputNoData.append(outNoData)

    def __addOutput__(self,outRaster,outNBand,outGdalGDT):
        if not os.path.exists(os.path.dirname(outRaster)):
            os.makedirs(os.path.dirname(outRaster))
        dst_ds = self.driver.Create(outRaster, self.nc,self.nl, outNBand, outGdalGDT)
        dst_ds.SetGeoTransform(self.GeoTransform)
        dst_ds.SetProjection(self.Projection)
        self.outputs.append(dst_ds)
        
    def __iterBlock__(self,getBlock=False):       
        for row in range(0, self.nl, self.y_block_size):
            for col in range(0, self.nc, self.x_block_size):
                width = min(self.nc - col, self.x_block_size)
                height = min(self.nl - row, self.y_block_size)
                
                if getBlock :
                    X,mask = self.generateBlockArray(col,row,width,height,self.mask)
                    yield X,mask,col,row,width,height
                else:
                    yield col,row,width,height
    
    def generateBlockArray(self,col,row,width,height,mask=True):       
        arr = np.empty((height*width,self.nb))
        
        for ind in range(self.nb):
            band = self.openRaster.GetRasterBand(int(ind+1))
            arr[:,ind] = band.ReadAsArray(col,row,width,height).reshape(width*height)
        if mask:
            arrMask = self.openMask.GetRasterBand(1).ReadAsArray(col,row,width,height).reshape(width*height)
        else:
            arrMask=None
            
        arr,arrMask = self.filterNoData(arr,arrMask)    
        
        return arr,arrMask
    
    def filterNoData(self,arr,mask=None):
        outArr = np.zeros((arr.shape))
        outArr[:] = self.nodata
        
        if self.mask :
            t = np.logical_or((mask==self.maskNoData),arr[:,0]==self.nodata)            
        else:
            t = np.where(arr[:,0]==self.nodata)
            
        tmpMask = np.ones(arr.shape,dtype=bool)            
        tmpMask[t,:] = False
        outArr[tmpMask] = arr[tmpMask]

        return outArr,tmpMask
    
    def getRandomBlock(self):    
        cols = int(np.random.permutation(range(0,self.nl,self.y_block_size))[0])
        lines = int(np.random.permutation(range(0,self.nc,self.x_block_size))[0])
        width = min(self.nc - lines, self.x_block_size)
        height = min(self.nl - cols, self.y_block_size)
    
        tmp,mask = self.generateBlockArray(lines,cols,width,height,self.mask)
        arr = tmp[mask[:,0],:]
        return arr
    
                
    def run(self,verbose=1,qgsFeedback=False):
        """
        Process with outside function.
        """          
        
        # TODO : Parallel/ Not working for now.
        if self.parallel :
            try:
                from joblib import Parallel, delayed  
            except :
                raise ImportError('Please install joblib to use multiprocessing')
            def processParallel(X,mask,i,j,cols,lines,outputNBand,fun):                
                tmp = np.copy(X)
                tmp[mask[:,0],:outputNBand] = fun(tmp[mask[:,0],:])
                
                return tmp,mask,i,j,cols,lines,idx
                
                #return X
            #self.resFromIterBlock= []
            #self.resFromIterBlock.extend(self.__iterBlock__(getBlock=False))
            
            for idx,fun in enumerate(self.functions):
                outputNBand = self.outputs[idx].RasterCount 
                for X,mask,i,j,cols,lines,idx in Parallel(n_jobs=self.parallel)(delayed(processParallel)(X,mask,i,j,cols,lines,outputNBand,fun) for X,mask,i,j,cols,lines in self.__iterBlock__(getBlock=True)):
                    if verbose:
                        self.pb.addPosition(j)
                    #for X,mask,i,j,cols,lines,idx in Parallel(n_jobs=self.parallel,verbose=False)(delayed(processParallel)(X,mask,i,j,cols,lines,outputNBand,fun) for X,mask,i,j,cols,lines in self.__iterBlock__(getBlock=True)):
                    for ind in range(self.outputs[idx].RasterCount):
                        indGdal = int(ind+1)
                        curBand = self.outputs[idx].GetRasterBand(indGdal)
                        curBand.WriteArray(X[:,ind].reshape(lines,cols),i,j)
                        curBand.FlushCache()
                    self.outputs[idx].GetRasterBand(1).SetNoDataValue(self.outNoData)

        else:
        
            for X,mask,col,line,cols,lines in self.__iterBlock__(getBlock=True):
                X_ = np.copy(X)
                actualProgress = int((line+1)/self.total*100)                
                
                
                if self.lastProgress != actualProgress:
                    self.lastProgress = actualProgress 
    
                    if qgsFeedback:
                        if qgsFeedback == 'gui':                        
                            self.pb.addPosition(line)
                        else:
                            qgsFeedback.setProgress(actualProgress)
                            if qgsFeedback.isCanceled():
                                break
                        
                    if verbose:
                        
                        self.pb.addPosition(line)
                    
                for idx,fun in enumerate(self.functions):
                    if self.outputNoData[idx] == False:
                        self.outputNoData[idx] = self.nodata
                        
                    maxBands = self.outputs[idx].RasterCount
                    if X_[mask].size > 0:
                        resFun = fun(X_[mask[:,0],:])
                        if maxBands > self.nb:
                            X = np.zeros((X_.shape[0],maxBands))
                            X[:,:] = self.outputNoData[idx]
                            X[mask[:,0],:] = resFun
                        if resFun.ndim == 1:
                            resFun = resFun.reshape(-1,1)
                        if resFun.shape[1] > maxBands :
                            raise ValueError ("Your function output {} bands, but your output is specified to have a maximum of {} bands.".format(resFun.shape[1],maxBands))
                        else:
                            X[:,:] = self.outputNoData[idx]
                            X[mask[:,0],:maxBands] = resFun
                    for ind in range(self.outputs[idx].RasterCount):
                        indGdal = int(ind+1)
                        curBand = self.outputs[idx].GetRasterBand(indGdal)
                        curBand.WriteArray(X[:,ind].reshape(lines,cols),col,line)
                        curBand.FlushCache()
                    
                    band = self.outputs[idx].GetRasterBand(1)
                    band.SetNoDataValue(self.outputNoData[idx])
                    band.FlushCache()
            band=None
            for idx,fun in enumerate(self.functions):
                print('Saved {} using function {}'.format(self.outputs[idx].GetDescription(),str(fun.__name__)))
                self.outputs[idx] = None