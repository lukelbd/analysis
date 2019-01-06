#!/usr/bin/env python3
"""
Various geographic utilities. Includes calculus on spherical geometry
and some other stuff. Padding arrays and whatnot.
"""
import numpy as np
from . import const

# Helper class
# TODO: Obsolete? This was dumb, was just trying to learn about classes
class GridDes(object):
    """
    For storing latitude/longitude grid properties. Assumes global grid, and
    borders halfway between each grid center.
    """
    def __init__(self, lon, lat):
        # First, guess cell widths and edges
        lon, lat = lon.astype(np.float32), lat.astype(np.float32)
        dlon1, dlon2 = lon[1]-lon[0], lon[-1]-lon[-2]
        dlat1, dlat2 = lat[1]-lat[0], lat[-1]-lat[-2]
        self.latb = np.concatenate((lat[:1]-dlat1/2, (lat[1:]+lat[:-1])/2, lat[-1:]+dlat2/2))
        self.lonb = np.concatenate((lon[:1]-dlon1/2, (lon[1:]+lon[:-1])/2, lon[-1:]+dlon2/2))
        self.latc, self.lonc = lat.copy(), lon.copy()

        # Use corrections for dumb grids with 'centers' at poles
        if lat[0]==-90:
            self.latc[0], self.latb[0] = -90 + dlat1/4, -90
        if lat[-1]==90:
            self.latc[-1], self.latb[-1] = 90 - dlat2/4, 90

        # Corrected grid widths (cells half as tall near pole)
        self.dlon = self.lonb[1:]-self.lonb[:-1]
        self.dlat = self.latb[1:]-self.latb[:-1]
        if lat[0]==-90:
            self.dlat[0] /= 2
        if lat[-1]==90:
            self.dlat[-1] /= 2

        # Radians
        self.phic, self.phib, self.dphi = self.latc*np.pi/180, self.latb*np.pi/180, self.dlat*np.pi/180
        self.thetac, self.thetab, self.dtheta = self.lonc*np.pi/180, self.lonb*np.pi/180, self.dlon*np.pi/180

        # Area weights (function of latitude only). Close approximation to area,
        # since cosine is extremely accurate. Also make lon by lat, so
        # broadcasting rules can apply.
        self.weights = self.dphi[None,:]*self.dtheta[:,None]*np.cos(self.phic[None,:])
        self.areas = self.dphi[None,:]*self.dtheta[:,None]*np.cos(self.phic[None,:])*(const.a**2)
        # areas = dphi*dtheta*np.cos(phic)*(const.a**2)[None,:]

    def __repr__(self, n=3): # what happens when viewing in interactive session
        return f'''
latc: {', '.join(f'{self.latc[i]: 7.2f}' for i in range(n))} ... {self.latc[-1]: .2f}
latb: {', '.join(f'{self.latb[i]: 7.2f}' for i in range(n))} ... {self.latb[-1]: .2f}
dlat: {', '.join(f'{self.dlat[i]: 7.2f}' for i in range(n))} ... {self.dlat[-1]: .2f}
lonc: {', '.join(f'{self.lonc[i]: 7.2f}' for i in range(n))} ... {self.lonc[-1]: .2f}
lonb: {', '.join(f'{self.lonb[i]: 7.2f}' for i in range(n))} ... {self.lonb[-1]: .2f}
dlon: {', '.join(f'{self.dlon[i]: 7.2f}' for i in range(n))} ... {self.dlon[-1]: .2f}
  Replace 'lat' with 'phi', 'lon' with 'theta' for radians.
  See 'areas' for grid cell geographic areas.
'''

def geopad(lon, lat, data, nlon=1, nlat=0):
    """
    Returns array padded circularly along lons, and over the earth pole,
    for finite difference methods.
    """
    # Get padded array
    if nlon>0:
        pad = ((nlon,nlon),) + (data.ndim-1)*((0,0),)
        data = np.pad(data, pad, mode='wrap')
        lon = np.pad(lon, nlon, mode='wrap') # should be vector
    if nlat>0:
        if (data.shape[0] % 2)==1:
            raise ValueError('Data must have even number of longitudes, if you wish to pad over the poles.')
        data_append = np.roll(np.flip(data, axis=1), data.shape[0]//2, axis=0)
            # data is now descending in lat, and rolled 180 degrees in lon
        data = np.concatenate((
            data_append[:,-nlat:,...], # -87.5, -88.5, -89.5 (crossover)
            data, # -89.5, -88.5, -87.5, ..., 87.5, 88.5, 89.5 (crossover)
            data_append[:,:nlat,...], # 89.5, 88.5, 87.5
            ), axis=1)
        lat = np.pad(lat, nlat, mode='symmetric')
        lat[:nlat], lat[-nlat:] = 180-lat[:nlat], 180-lat[-nlat:]
            # much simpler for lat; but want monotonic ascent, so allow these to be >90, <-90
    return lon, lat, data

def geomean(lon, lat, data, box=(None,None,None,None),
        landfracs=None, mode=None, weights=1, keepdims=False):
    """
    Takes area mean of data time series; zone and F are 2d, but data is 3d.
    Since array is masked, this is super easy... just use the masked array
    implementation of the mean, and it will adjust weights accordingly.

    Parameters
    ----------
    lon :
        grid longitude centers
    lat :
        grid latitude centers
    landfracs :
        to be used by mode, above
    data :
        should be lon by lat by (extra dims); will preserve dimensionality.
    box :
        mean-taking region; note if edges don't fall on graticule, will just subsample
        the grid cells that do -- haven't bothered to account for partial coverage, because
        it would be pain in the butt and not that useful.
    weights: extra, custom weights to apply to data -- could be land/ocean fractions, for example.

    Notes
    -----
    Data should be loaded with myfuncs.ncutils.ncload, and provide this function
    with metadata in 'm' structure.
    """
    # Get cell areas
    a = GridDes(lon, lat).areas

    # Get zone for average
    delta = lat[1]-lat[0]
    zone = np.ones((1,lat.size), dtype=bool)
    if box[1] is not None: # south
        zone = zone & ((lat[:-1]-delta/2 >= box[1])[None,:])
    if box[3] is not None: # north
        zone = zone & ((lat[1:]+delta/2 <= box[3])[None,:])

    # Get lune for average
    delta = lon[1]-lon[0]
    lune = np.ones((lon.size,1), dtype=bool)
    if box[0] is not None: # west
        lune = lune & ((lon[:-1]-delta/2 >= box[0])[:,None]) # left-hand box edges >= specified edge
    if box[2] is not None: # east
        lune = lune & ((lon[1:]+delta/2 <= box[2])[:,None]) # right-hand box edges <= specified edge

    # Get total weights
    weights = a*zone*lune*weights
    for s in data.shape[2:]:
        weights = weights[...,None]
    weights = np.tile(weights, (1,1,*data.shape[2:])) # has to be tiled, to match shape of data exactly

    # And apply; note that np.ma.average was tested to be slower than the
    # three-step procedure for NaN ndarrays used below
    if type(data) is np.ma.MaskedArray:
        data = data.filled(np.nan)
    isvalid = np.isfinite(data) # boolean function extremely fast
    data[~isvalid] = 0 # scalar assignment extremely fast
    try: ave = np.average(data, weights=weights*isvalid, axis=(0,1))
    except ZeroDivisionError:
        ave = np.nan # weights sum to zero

    # Return, optionally restoring the lon/lat dimensions to singleton
    if keepdims:
        return ave[None,None,...]
    else:
        return ave

def haversine(lon1, lat1, lon2, lat2):
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)

    Parameters
    ----------
    lon1, lat1, lon2, lat2 : ndarrays
        ndarrays of longitude and latitude in degrees
        * Each **pair** should have identical shape
        * If both pairs are non-scalar, they must **also** be identically shaped
        * If one pair is scalar, distances are calculated between the scalar pair
          and each element of the non-scalar pari.

    Returns
    -------
    d : ndarray
        distances in km
    """
    # Earth radius, in km
    R = const.a*1e-3

    # Convert to radians, get differences
    lon1, lat1, lon2, lat2 = map(np.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1

    # Haversine, in km
    km = 2.*R*np.arcsin(np.sqrt(
        np.sin(dlat/2.)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2.)**2
        ))
    return km

def laplacian(lon, lat, data, accuracy=4):
    """
    Get Laplacian in spherical coordinates.

    Input
    -----
    lon, lat : ndarrays
        longitude and latitude
    data : ndarray
        the data

    Equation
    --------
    del^2 = (1/a^2*cos^2(phi)) * (d/dtheta)^2
          + (1/a^2*cos(phi))   * (d/dphi)(cos(phi)*d/dphi)
    """
    # Setup
    npad = accuracy//2 # need +/-1 for O(h^2) approx, +/-2 for O(h^4), etc.
    data = geopad(lon, lat, data, nlon=npad, nlat=npad)[2] # pad lons/lats
    phi, theta = lat*np.pi/180, lon*np.pi/180 # from north pole

    # Execute
    h_phi, h_theta = abs(phi[2]-phi[1]), abs(theta[2]-theta[1]) # avoids weird edge cases
    phi = phi[None,...]
    for i in range(2,data.ndim):
        phi = phi[...,None]
    laplacian = ( # below avoids repeating finite differencing scheme
            (1/(const.a**2 * np.cos(phi)**2)) * deriv2(h_theta, data[:,npad:-npad,...], axis=0, accuracy=accuracy) # unpad latitudes
            + (-np.tan(phi)/(const.a**2)) * deriv1(h_phi, data[npad:-npad,...], axis=1, accuracy=accuracy) # unpad longitudes
            + (1/(const.a**2)) * deriv2(h_phi, data[npad:-npad,...], axis=1, accuracy=accuracy) # unpad longitudes
            ) # note, no axis rolling required here; the deriv schemes do that
    return laplacian

