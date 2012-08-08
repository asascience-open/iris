# (C) British Crown Copyright 2010 - 2012, Met Office
#
# This file is part of Iris.
#
# Iris is free software: you can redistribute it and/or modify it under
# the terms of the GNU Lesser General Public License as published by the
# Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Iris is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with Iris.  If not, see <http://www.gnu.org/licenses/>.
"""
Calculus operations on :class:`iris.cube.Cube` instances.

See also: :mod:`NumPy <numpy>`.

"""

from __future__ import division
import re
import warnings

import numpy

import iris.cube
import iris.coords
import iris.coord_systems
import iris.analysis
import iris.analysis.maths 
import iris.analysis.cartography
from iris.util import delta


__all__ = ['cube_delta', 'differentiate', 'curl']


def _construct_delta_coord(coord):
    """
    Return a coordinate of deltas between the given coordinate's points. If the original coordinate has length n
    and is circular then the result will be a coordinate of length n, otherwise the result will be
    of length n-1.

    """
    if coord.ndim != 1:
        raise iris.exceptions.CoordinateMultiDimError(coord)
    circular = getattr(coord, 'circular', False)
    if coord.shape == (1,) and not circular:
        raise ValueError('Cannot take interval differences of a single valued coordinate.')

    if circular:
        circular_kwd = coord.units.modulus or True
    else:
        circular_kwd = False

    if coord.bounds is not None:
        bounds = iris.util.delta(coord.bounds, 0, circular=circular_kwd)
    else:
        bounds = None
                
    points = iris.util.delta(coord.points, 0, circular=circular_kwd)
    new_coord = iris.coords.AuxCoord.from_coord(coord).copy(points, bounds)
    new_coord.rename('change_in_%s' % new_coord.name())

    return new_coord


def _construct_midpoint_coord(coord, circular=None):
    """
    Return a coordinate of mid-points from the given coordinate. If the given coordinate has length n
    and the circular flag set then the result will be a coordinate of length n, otherwise the result will be
    of length n-1.

    """
    if circular and not hasattr(coord, 'circular'):
        raise ValueError("Cannot produce circular midpoint from a coord without the circular attribute ")

    if circular is None:
        circular = getattr(coord, 'circular', False)
    elif circular != getattr(coord, 'circular', False):
        warnings.warn("circular flag and Coord.circular attribute do not match")

    if coord.ndim != 1:
        raise iris.exceptions.CoordinateMultiDimError(coord)
    if coord.shape == (1,) and not circular:
        raise ValueError('Cannot take the midpoints of a single valued coordinate.')

    # Calculate the delta of the coordinate (this deals with circularity nicely)
    mid_point_coord = _construct_delta_coord(coord)

    # if the coord is circular then include the last one, else, just take 0:-1
    circular_slice = slice(0, -1 if not circular else None)

    if coord.bounds is not None:
        axis_delta = mid_point_coord.bounds
        mid_point_bounds = axis_delta * 0.5 + coord.bounds[circular_slice, :]
    else:
        mid_point_bounds = None

    # Get the deltas
    axis_delta = mid_point_coord.points
    # Add half of the deltas to the original points
    # if the coord is circular then include the last one, else, just take 0:-1
    mid_point_points = axis_delta * 0.5 + coord.points[circular_slice]

    try: # try creating a coordinate of the same type as before, otherwise, make an AuxCoord
        mid_point_coord = coord.from_coord(coord).copy(mid_point_points, mid_point_bounds)
    except ValueError:
        mid_point_coord = iris.coords.AuxCoord.from_coord(coord).copy(mid_point_points, mid_point_bounds)
    
    # Set the coord name to the original name (as coord_delta will have modified it to change_in_*)
    mid_point_coord.rename(coord.name())

    return mid_point_coord


def cube_delta(cube, coord, update_history=True):
    """
    Given a cube calculate the difference between each value in the given coord's direction.
    

    Args:
    
    * coord 
        either a Coord instance or the unique name of a coordinate in the cube.
        If a Coord instance is provided, it does not necessarily have to exist in the cube.
    
    Example usage::
    
        change_in_temperature_wrt_pressure = cube_delta(temperature_cube, 'pressure')
    
    .. Note:: Missing data support not yet implemented.
    
    """
    # handle the case where a user passes a coordinate name
    if isinstance(coord, basestring):
        coord = cube.coord(coord)

    if coord.ndim != 1:
        raise iris.exceptions.CoordinateMultiDimError(coord)

    # Try and get a coord dim
    delta_dims = cube.coord_dims(coord)
    if (coord.shape[0] == 1 and not getattr(coord, 'circular', False)) or not delta_dims:
        raise ValueError('Cannot calculate delta over "%s" as it has length of 1.' % coord.name())
    delta_dim = delta_dims[0]

    # Calculate the actual delta, taking into account whether the given coordinate is circular
    delta_cube_data = delta(cube.data, delta_dim, circular=getattr(coord, 'circular', False))

    # If the coord/dim is circular there is no change in cube shape
    if getattr(coord, 'circular', False):
        delta_cube = cube.copy(data=delta_cube_data)
    else:
        # Subset the cube to the appropriate new shape by knocking off the last row of the delta dimension
        subset_slice = [slice(None,None)] * cube.ndim
        subset_slice[delta_dim] = slice(None, -1)
        delta_cube = cube[tuple(subset_slice)]
        delta_cube.data = delta_cube_data

    # Replace the delta_dim coords with midpoints (no shape change if circular).
    for cube_coord in cube.coords(dimensions=delta_dim):
        delta_cube.replace_coord(_construct_midpoint_coord(cube_coord, circular=getattr(coord, 'circular', False)))

    if update_history:
        # Add history
        delta_cube.add_history('Delta of %s wrt %s' % (delta_cube.name(), coord.name()))
    
    delta_cube.rename('change_in_%s_wrt_%s' % (delta_cube.name(), coord.name()))
     
    return delta_cube


def differentiate(cube, coord_to_differentiate):
    r"""
    Calculate the differential of a given cube with respect to the coord_to_differentiate.
    
    Args:

    * coord_to_differentiate:
        Either a Coord instance or the unique name of a coordinate which exists in the cube.
        If a Coord instance is provided, it does not necessarily have to exist on the cube.

    Example usage::
    
        u_wind_acceleration = differentiate(u_wind_cube, 'forecast_time')

    The algorithm used is equivalent to:
    
    .. math::
    
        d_i = \frac{v_{i+1}-v_i}{c_{i+1}-c_i}
    
    Where ``d`` is the differential, ``v`` is the data value, ``c`` is the coordinate value and ``i`` is the index in the differential
    direction. Hence, in a normal situation if a cube has a shape (x: n; y: m) differentiating with respect to x will result in a cube
    of shape (x: n-1; y: m) and differentiating with respect to y will result in (x: n; y: m-1). If the coordinate to differentiate is
    :attr:`circular <iris.coords.DimCoord.circular>` then the resultant shape will be the same as the input cube. 
    

    .. note:: Difference method used is the same as :func:`cube_delta` and therefore has the same limitations.
    
    .. note:: Spherical differentiation does not occur in this routine.

    """
    # Get the delta cube in the required differential direction. Don't add this to the resultant
    # cube's history as we will do that ourself.
    # This operation results in a copy of the original cube.
    delta_cube = cube_delta(cube, coord_to_differentiate, update_history=False)
    
    if isinstance(coord_to_differentiate, basestring):
        coord = cube.coord(coord_to_differentiate)
    else:
        coord = coord_to_differentiate
    
    delta_coord = _construct_delta_coord(coord)
    delta_dim = cube.coord_dims(coord)[0]

    # calculate delta_cube / delta_coord to give the differential. Don't update the history, as we will
    # do this ourself.
    delta_cube = iris.analysis.maths.divide(delta_cube, delta_coord, delta_dim,
                                            update_history=False)

    # Update the history of the new cube
    delta_cube.add_history('differential of %s wrt to %s' % (cube.name(), coord.name()) )
    
    # Update the standard name
    delta_cube.rename(('derivative_of_%s_wrt_%s' % (cube.name(), coord.name())) )
    return delta_cube


def _curl_subtract(a, b):
    """
    Simple wrapper to :func:`iris.analysis.maths.subtract` to subtract two cubes, which deals with None in a way that makes sense in the context of curl.

    """
    # We are definitely dealing with cubes or None - otherwise we have a programmer error...
    assert isinstance(a, iris.cube.Cube) or a is None
    assert isinstance(b, iris.cube.Cube) or b is None
    
    if a is None and b is None:
        return None
    elif a is None:
        c = b.copy(data = 0 - b.data)
        return c
    elif b is None:
        return a.copy()
    else:
        return iris.analysis.maths.subtract(a, b, update_history=False)


def _curl_differentiate(cube, coord):
    """
    Simple wrapper to :func:`differentiate` to differentiate a cube and deal with None in a way that makes sense in the context of curl.

    """
    # We are definitely dealing with cubes/coords or None - otherwise we have a programmer error...
    assert isinstance(cube, iris.cube.Cube) or cube is None
    assert isinstance(coord, iris.coords.Coord) or coord is None
    
    if cube is None:
        return None
    if coord.ndim != 1:
        raise iris.exceptions.CoordinateMultiDimError(coord)
    if coord.shape[0] <= 1:
        return None
    
    return differentiate(cube, coord)


def _curl_regrid(cube, prototype):
    """
    Simple wrapper to :ref`iris.cube.Cube.regridded` to deal with None in a way that makes sense in the context of curl.
    
    """
    # We are definitely dealing with cubes or None - otherwise we have a programmer error...
    assert isinstance(cube, iris.cube.Cube) or cube is None
    assert isinstance(prototype, iris.cube.Cube)
    
    if cube is None:
        return None
    # #301 use of resample would be better here.
    return cube.regridded(prototype)


def _copy_cube_transformed(src_cube, data, coord_func):
    """
    Returns a new cube based on the src_cube, but with the given data,
    and with the coordinates transformed via coord_func.

    The data must have the same number of dimensions as the source cube.

    """
    assert src_cube.ndim == data.ndim

    # Start with just the metadata and the data...
    new_cube = iris.cube.Cube(data)
    new_cube.metadata = src_cube.metadata

    # ... and then create all the coordinates.

    # Record a mapping from old coordinate IDs to new coordinates,
    # for subsequent use in creating updated aux_factories.
    coord_mapping = {}

    def copy_coords(source_coords, add_method):
        for coord in source_coords:
            new_coord = coord_func(coord)
            add_method(new_coord, src_cube.coord_dims(coord))
            coord_mapping[id(coord)] = new_coord

    copy_coords(src_cube.dim_coords, new_cube.add_dim_coord)
    copy_coords(src_cube.aux_coords, new_cube.add_aux_coord)

    for factory in src_cube.aux_factories:
        new_cube.add_aux_factory(factory.updated(coord_mapping))

    return new_cube


def _curl_change_z(src_cube, z_coord, prototype_diff):
    # New data
    ind = [slice(None, None)] * src_cube.data.ndim 
    z_dim = src_cube.coord_dims(z_coord)[0] 
    ind[z_dim] = slice(-1, None) 
    new_data = numpy.append(src_cube.data, src_cube.data[tuple(ind)], z_dim)
    
    # The existing z_coord doesn't fit the new data so make a
    # new cube using the prototype z_coord.
    local_z_coord = src_cube.coord(coord=z_coord)
    new_local_z_coord = prototype_diff.coord(coord=z_coord).copy()
    def coord_func(coord):
        if coord is local_z_coord:
            new_coord = new_local_z_coord
        else:
            new_coord = coord.copy()
        return new_coord
    result = _copy_cube_transformed(src_cube, new_data, coord_func)
    return result


def curl(i_cube, j_cube, k_cube=None, ignore=None, update_history=True):
    r'''
    Calculate the 3d curl of the given vector of cubes.

    Args:
    
    * i_cube
        The i cube of the vector to operate on
    * j_cube
        The j cube of the vector to operate on
        
    Kwargs:
    
    * k_cube
        The k cube of the vector to operate on        

    Return (i_cmpt_curl_cube, j_cmpt_curl_cube, k_cmpt_curl_cube)
    
    The calculation of curl is dependent on the type of :func:`iris.coord_systems.HorizontalCS` in the cube:
    
        Cartesian curl
        
            The Cartesian curl is defined as:
        
            .. math::
            
                \nabla\times \vec u = (\frac{\delta w}{\delta y} - \frac{\delta v}{\delta z}) \vec a_i - (\frac{\delta w}{\delta x} - \frac{\delta u}{\delta z})\vec a_j + (\frac{\delta v}{\delta x} - \frac{\delta u}{\delta y})\vec a_k
        
        Spherical curl
            
            When spherical calculus is used, i_cube is the phi vector component (e.g. eastward), j_cube is the theta component 
            (e.g. northward) and k_cube is the radial component.
    
            The spherical curl is defined as:
        
            .. math::
                
                \nabla\times \vec A = \frac{1}{r cos \theta}(\frac{\delta}{\delta \theta}(\vec A_\phi cos \theta) - \frac{\delta \vec A_\theta}{\delta \phi}) \vec r + \frac{1}{r}(\frac{1}{cos \theta} \frac{\delta \vec A_r}{\delta \phi} - \frac{\delta}{\delta r} (r \vec A_\phi))\vec \theta + \frac{1}{r}(\frac{\delta}{\delta r}(r \vec A_\theta) - \frac{\delta \vec A_r}{\delta \theta}) \vec \phi
    
            where phi is longitude, theta is latitude.

    '''
    if ignore is not None:
        ignore = None
        warnings.warn('The ignore keyword to iris.analysis.calculus.curl is deprecated, ignoring is now done automatically.')
    
    # get the radius of the earth
    latlon_cs = i_cube.coord_system(iris.coord_systems.LatLonCS)
    if latlon_cs and latlon_cs.datum.is_spherical():
        r = latlon_cs.datum.semi_major_axis
        r_unit = latlon_cs.datum.units
    else:
        r = iris.analysis.cartography.DEFAULT_SPHERICAL_EARTH_RADIUS
        r_unit = iris.analysis.cartography.DEFAULT_SPHERICAL_EARTH_RADIUS_UNIT


    # Get the vector quantity names (i.e. ['easterly', 'northerly', 'vertical'])
    vector_quantity_names, phenomenon_name = spatial_vectors_with_phenom_name(i_cube, j_cube, k_cube)
    
    cubes = filter(None, [i_cube, j_cube, k_cube])
    
    # get the names of all coords binned into useful comparison groups
    coord_comparison = iris.analysis.coord_comparison(*cubes)
    
    bad_coords = coord_comparison['ungroupable_and_dimensioned']
    if bad_coords:
        raise ValueError("Coordinates found in one cube that describe a data dimension which weren't in the other "
                         "cube (%s), try removing this coordinate."  % ', '.join([group.name() for group in bad_coords]))
    
    bad_coords = coord_comparison['resamplable']
    if bad_coords:
        raise ValueError('Some coordinates are different (%s), consider resampling.' % ', '.join([group.name() for group in bad_coords]))
    
    ignore_string = ''
    if coord_comparison['ignorable']:
        ignore_string = ' (ignoring %s)' % ', '.join([group.name() for group in bad_coords])

    # Get the dim_coord, or None if none exist, for the xyz dimensions
    x_coord = i_cube.coord(axis='X') 
    y_coord = i_cube.coord(axis='Y')
    z_coord = i_cube.coord(axis='Z')
    
    y_dim = i_cube.coord_dims(y_coord)[0]
   
    horiz_cs = i_cube.coord_system('HorizontalCS')
    if horiz_cs is None:
        raise ValueError('Could not get the horizontal CS of the cubes provided.')
        
    if horiz_cs.cs_type == iris.coord_systems.CARTESIAN_CS:
        
        # TODO Implement some mechanism for conforming to a common grid
        dj_dx = _curl_differentiate(j_cube, x_coord)
        prototype_diff = dj_dx
                
        # i curl component (dk_dy - dj_dz)
        dk_dy = _curl_differentiate(k_cube, y_coord)
        dk_dy = _curl_regrid(dk_dy, prototype_diff)
        dj_dz = _curl_differentiate(j_cube, z_coord)
        dj_dz = _curl_regrid(dj_dz, prototype_diff)
        
        # TODO Implement resampling in the vertical (which regridding does not support).
        if dj_dz is not None and dj_dz.data.shape != prototype_diff.data.shape:
            dj_dz = _curl_change_z(dj_dz, z_coord, prototype_diff)

        i_cmpt = _curl_subtract(dk_dy, dj_dz)
        dj_dz = dk_dy = None
        
        # j curl component (di_dz - dk_dx)
        di_dz = _curl_differentiate(i_cube, z_coord)
        di_dz = _curl_regrid(di_dz, prototype_diff)
        
        # TODO Implement resampling in the vertical (which regridding does not support).
        if di_dz is not None and di_dz.data.shape != prototype_diff.data.shape:
            di_dz = _curl_change_z(di_dz, z_coord, prototype_diff)

        dk_dx = _curl_differentiate(k_cube, x_coord)
        dk_dx = _curl_regrid(dk_dx, prototype_diff)
        j_cmpt = _curl_subtract(di_dz, dk_dx)
        di_dz = dk_dx = None
        
        # k curl component ( dj_dx - di_dy)
        di_dy = _curl_differentiate(i_cube, y_coord)
        di_dy = _curl_regrid(di_dy, prototype_diff)
        # Since prototype_diff == dj_dx we don't need to recalculate dj_dx
#        dj_dx = _curl_differentiate(j_cube, x_coord)
#        dj_dx = _curl_regrid(dj_dx, prototype_diff)
        k_cmpt = _curl_subtract(dj_dx, di_dy)
        di_dy = dj_dx = None
        
        result = [i_cmpt, j_cmpt, k_cmpt]
    
    elif horiz_cs.cs_type == iris.coord_systems.SPHERICAL_CS:
        # A_\phi = i ; A_\theta = j ; A_\r = k
        # theta = lat ; phi = long ;
        # r_cmpt = 1/ ( r * cos(lat) ) * ( d/dtheta ( i_cube * sin( lat ) ) - d_j_cube_dphi )
        # phi_cmpt = 1/r * ( d/dr (r * j_cube) - d_k_cube_dtheta)
        # theta_cmpt = 1/r * ( 1/cos(lat) * d_k_cube_dphi - d/dr (r * i_cube)
        if not horiz_cs.datum.is_spherical():
            raise NotImplementedError('Cannot take the curl over a non-spherical datum.')
        
        if y_coord.name() != 'latitude' or x_coord.name() != 'longitude':
            raise ValueError('Expecting latitude as the y coord and longitude as the x coord for spherical curl.')
        
        lat_coord = y_coord.unit_converted('radians')
        # TODO: Can the use of lat_coord.cos() be replaced with lat_coord.nd_points.cos()?
        # Then we can get rid of Coord.sin() and Coord.cos().
        lat_cos_coord = lat_coord.cos()
        
        lon_coord = x_coord.unit_converted('radians')
        
        # TODO Implement some mechanism for conforming to a common grid
        temp = iris.analysis.maths.multiply(i_cube, lat_cos_coord, y_dim)
        dicos_dtheta = _curl_differentiate(temp, lat_coord)
        prototype_diff = dicos_dtheta
        
        # r curl component:  1/ ( r * cos(lat) ) * ( dicos_dtheta - d_j_cube_dphi )
        # Since prototype_diff == dicos_dtheta we don't need to recalculate dicos_dtheta
#        dicos_dtheta = _curl_differentiate(i_cube * lat_cos_coord, lat_coord)
#        prototype_diff = dicos_dtheta
#        dicos_dtheta = _curl_regrid(dicos_dtheta, prototype_diff)
        d_j_cube_dphi = _curl_differentiate(j_cube, lon_coord)
        d_j_cube_dphi = _curl_regrid(d_j_cube_dphi, prototype_diff)
        
        new_lat_cos_coord = d_j_cube_dphi.coord(name='latitude').cos()
        lat_dim = d_j_cube_dphi.coord_dims(d_j_cube_dphi.coord(name='latitude'))[0]
         
        r_cmpt = iris.analysis.maths.divide(_curl_subtract(dicos_dtheta, d_j_cube_dphi), r * new_lat_cos_coord, dim=lat_dim)
        r_cmpt.units = r_cmpt.units / r_unit
        d_j_cube_dphi = dicos_dtheta = None
        
        # phi curl component: 1/r * ( drj_dr - d_k_cube_dtheta)
        drj_dr = _curl_differentiate(r * j_cube, z_coord)
        if drj_dr is not None:
            drj_dr.units = drj_dr.units * r_unit
        drj_dr = _curl_regrid(drj_dr, prototype_diff)
        d_k_cube_dtheta = _curl_differentiate(k_cube, lat_coord)
        d_k_cube_dtheta = _curl_regrid(d_k_cube_dtheta, prototype_diff)
        if drj_dr is None and d_k_cube_dtheta is None:
            phi_cmpt = None
        else:
            phi_cmpt = 1/r * _curl_subtract(drj_dr, d_k_cube_dtheta)
            phi_cmpt.units = phi_cmpt.units / r_unit
            
        drj_dr = d_k_cube_dtheta = None
        
        # theta curl component: 1/r * ( 1/cos(lat) * d_k_cube_dphi - dri_dr )
        d_k_cube_dphi = _curl_differentiate(k_cube, lon_coord)
        d_k_cube_dphi = _curl_regrid(d_k_cube_dphi, prototype_diff)
        if d_k_cube_dphi is not None:
            d_k_cube_dphi = iris.analysis.maths.divide(d_k_cube_dphi, lat_cos_coord)
        dri_dr = _curl_differentiate(r * i_cube, z_coord)
        if dri_dr is not None:
            dri_dr.units = dri_dr.units * r_unit
        dri_dr = _curl_regrid(dri_dr, prototype_diff)
        if d_k_cube_dphi is None and dri_dr is None:
            theta_cmpt = None
        else:
            theta_cmpt = 1/r * _curl_subtract(d_k_cube_dphi, dri_dr)
            theta_cmpt.units = theta_cmpt.units / r_unit
        d_k_cube_dphi = dri_dr = None
        
        result = [phi_cmpt, theta_cmpt, r_cmpt]
    
    else:
        raise ValueError("Horizontal coord system neither cartesian nor spherical spheroid: %s %s (%s)" \
                         % (type(horiz_cs), horiz_cs.cs_type, horiz_cs.datum))
    
    for direction, cube in zip(vector_quantity_names, result):
        if cube is not None:
            cube.rename('%s curl of %s' % (direction, phenomenon_name))
        
            if update_history:
                # Add history in place
                if k_cube is None:
                    cube.add_history('%s cmpt of the curl of %s and %s%s' % \
                                     (direction, i_cube.name(), j_cube.name(), ignore_string))
                else:
                    cube.add_history('%s cmpt of the curl of %s, %s and %s%s' % \
                                     (direction, i_cube.name(), j_cube.name(), k_cube.name(), ignore_string))
        
    return result


def spatial_vectors_with_phenom_name(i_cube, j_cube, k_cube=None):
    """
    Given 2 or 3 spatially dependent cubes, return a list of the spatial coordinate names with appropriate phenomenon name.
    
    This routine is designed to identify the vector quantites which each of the cubes provided represent
    and return a list of their 3d spatial dimension names and associated phenomenon.
    For example, given a cube of "u wind" and "v wind" the return value would be (['u', 'v', 'w'], 'wind')::
    
        >>> spatial_vectors_with_phenom_name(u_wind_cube, v_wind_cube) #doctest: +SKIP
        (['u', 'v', 'w'], 'wind')
    
    """
    directional_names = (('u', 'v', 'w'), ('x', 'y', 'z'), ('i', 'j', 'k'),
                         ('eastward', 'northward', 'upward'),
                         ('easterly', 'northerly', 'vertical'), ('easterly', 'northerly', 'radial'))
    
    # Create a list of the standard_names of our incoming cubes (excluding the k_cube if it is None)
    cube_standard_names = [cube.name() for cube in (i_cube, j_cube, k_cube) if cube is not None]

    # Define a regular expr which represents (direction, phenomenon) from the standard name of a cube
    # e.g from "w wind" -> ("w", "wind")
    vector_qty = re.compile(r'([^\W_]+)[\W_]+(.*)')
    
    # Make a dictionary of {direction: phenomenon quantity}
    cube_directions, cube_phenomena = zip( *[re.match(vector_qty, std_name).groups() for std_name in cube_standard_names] )
    
    # Check that there is only one distinct phenomenon
    if len(set(cube_phenomena)) != 1:
        raise ValueError('Vector phenomenon name not consistent between vector cubes. Got '
                         'cube phenomena: %s; from standard names: %s.' % \
                         (', '.join(cube_phenomena), ', '.join(cube_standard_names))
                         )
    
    # Get the appropriate direction list from the cube_directions we have got from the standard name
    direction = None
    for possible_direction in directional_names:
        # if this possible direction (minus the k_cube if it is none) matches direction from the given cubes use it.
        if possible_direction[0:len(cube_directions)] == cube_directions:
            direction = possible_direction
    
    # If we didn't get a match, raise an Exception
    if direction is None:
        direction_string = '; '.join((', '.join(possible_direction) for possible_direction in directional_names))
        raise ValueError('%s are not recognised vector cube_directions. Possible cube_directions are: %s.' % \
                         (cube_directions, direction_string) )

    return (direction, cube_phenomena[0])