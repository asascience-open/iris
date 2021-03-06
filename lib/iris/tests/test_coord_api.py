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


from __future__ import division

# import iris tests first so that some things can be initialised before importing anything else
import iris.tests as tests

import unittest
from xml.dom.minidom import Document
import logging

import numpy as np

import iris
import iris.aux_factory
import iris.coord_systems
import iris.coords
import iris.exceptions
import iris.unit
import iris.tests.stock


logger = logging.getLogger('tests')


class TestLazy(unittest.TestCase):
    def setUp(self):
        # Start with a coord with LazyArray points.
        shape = (3, 4)
        point_func = lambda: np.arange(12).reshape(shape)
        points = iris.aux_factory.LazyArray(shape, point_func)
        self.coord = iris.coords.AuxCoord(points=points)

    def _check_lazy(self, coord):
        self.assertIsInstance(self.coord._points, iris.aux_factory.LazyArray)
        self.assertIsNone(self.coord._points._array)

    def test_nop(self):
        self._check_lazy(self.coord)

    def _check_both_lazy(self, new_coord):
        # Make sure both coords have an "empty" LazyArray.
        self._check_lazy(self.coord)
        self._check_lazy(new_coord)

    def test_lazy_slice1(self):
        self._check_both_lazy(self.coord[:])

    def test_lazy_slice2(self):
        self._check_both_lazy(self.coord[:, :])

    def test_lazy_slice3(self):
        self._check_both_lazy(self.coord[...])

    def _check_concrete(self, new_coord):
        # Taking a genuine subset slice should trigger the evaluation
        # of the original LazyArray, and result in a normal ndarray for
        # the new coord.
        self.assertIsInstance(self.coord._points, iris.aux_factory.LazyArray)
        self.assertIsInstance(self.coord._points._array, np.ndarray)
        self.assertIsInstance(new_coord._points, np.ndarray)

    def test_concrete_slice1(self):
        self._check_concrete(self.coord[0])

    def test_concrete_slice2(self):
        self._check_concrete(self.coord[0, :])

    def test_shape(self):
        # Checking the shape shouldn't trigger a lazy load.
        self.assertEqual(self.coord.shape, (3, 4))
        self._check_lazy(self.coord)

    def _check_shared_data(self, coord):
        # Updating the original coord's points should update the sliced
        # coord's points too.
        points = coord.points
        new_points = coord[:].points
        np.testing.assert_array_equal(points, new_points)
        points[0, 0] = 999
        self.assertEqual(points[0, 0], new_points[0, 0])

    def test_concrete_shared_data(self):
        coord = iris.coords.AuxCoord(np.arange(12).reshape((3, 4)))
        self._check_shared_data(coord)

    def test_lazy_shared_data(self):
        self._check_shared_data(self.coord)


class TestCoordSlicing(unittest.TestCase):
    def setUp(self):
        cube = iris.tests.stock.realistic_4d()
        self.lat = cube.coord('grid_latitude')
        self.surface_altitude = cube.coord('surface_altitude')
        
    def test_slice_copy(self):
        a = self.lat
        b = a.copy()
        self.assertEqual(a, b)
        self.assertFalse(a is b)
        
        a = self.lat
        b = a[:]
        self.assertEqual(a, b)
        self.assertFalse(a is b)
        
    def test_slice_multiple_indices(self):
        aux_lat = iris.coords.AuxCoord.from_coord(self.lat)
        aux_sliced = aux_lat[(3, 4), :]
        dim_sliced   = self.lat[(3, 4), :]
        
        self.assertEqual(dim_sliced, aux_sliced)

    def test_slice_reverse(self):
        b = self.lat[::-1]
        np.testing.assert_array_equal(b.points, self.lat.points[::-1])
        np.testing.assert_array_equal(b.bounds, self.lat.bounds[::-1, :])
        
        c = b[::-1]
        self.assertEqual(self.lat, c)
        
    def test_multidim(self):
        a = self.surface_altitude
        # make some arbitrary bounds
        bound_shape = a.shape + (2,)
        a.bounds = np.arange(np.prod(bound_shape)).reshape(bound_shape)
        b = a[(0, 2), (0, -1)]
        np.testing.assert_array_equal(b.points, a.points[(0, 2), :][:, (0, -1)])
        np.testing.assert_array_equal(b.bounds, a.bounds[(0, 2), :, :][:, (0, -1), :])


class TestCoordIntersection(tests.IrisTest):
    def setUp(self):
        self.a = iris.coords.DimCoord(np.arange(9., dtype=np.float32) * 3 + 9., long_name='foo', units='meter')# 0.75)
        self.a.guess_bounds(0.75)
        pts = np.array([  3.,   6.,   9.,  12.,  15.,  18.,  21.,  24.,  27.,  30.], dtype=np.float32)
        bnds = np.array([[  0.75,   3.75],
           [  3.75,   6.75],
           [  6.75,   9.75],
           [  9.75,  12.75],
           [ 12.75,  15.75],
           [ 15.75,  18.75],
           [ 18.75,  21.75],
           [ 21.75,  24.75],
           [ 24.75,  27.75],
           [ 27.75,  30.75]], dtype=np.float32)
        self.b = iris.coords.AuxCoord(pts, long_name='foo', units='meter', bounds=bnds)
    
    def test_basic_intersection(self):
        inds = self.a.intersect(self.b, return_indices=True)
        self.assertEqual((0, 1, 2, 3, 4, 5, 6, 7), tuple(inds))
            
        c = self.a.intersect(self.b)
        self.assertXMLElement(c, ('coord_api', 'intersection.xml'))
    
    def test_intersection_reverse(self):
        inds = self.a.intersect(self.b[::-1], return_indices=True)    
        self.assertEqual((7, 6, 5, 4, 3, 2, 1, 0), tuple(inds))
        
        c = self.a.intersect(self.b[::-1])
        self.assertXMLElement(c, ('coord_api', 'intersection_reversed.xml'))
    
    def test_no_intersection_on_points(self):    
        # Coordinates which do not share common points but with common bounds should fail
        self.a.points = self.a.points + 200
        self.assertRaises(ValueError, self.a.intersect, self.b)
        
    def test_intersection_one_fewer_upper_bound_than_lower(self):
        self.b.bounds[4, 1] = self.b.bounds[0, 1]        
        c = self.a.intersect(self.b)
        self.assertXMLElement(c, ('coord_api', 'intersection_missing.xml'))
        
    def test_no_intersection_on_bounds(self):        
        # Coordinates which do not share common bounds but with common points should fail
        self.a.bounds = None
        a = self.a.copy()
        a.bounds = None
        a.guess_bounds(bound_position=0.25)
        self.assertRaises(ValueError, a.intersect, self.b)
    
    def test_no_intersection_on_name(self):
        # Coordinates which do not share the same name should fail
        self.a.long_name = 'foobar'
        self.assertRaises(ValueError, self.a.intersect, self.b)
        
    def test_no_intersection_on_unit(self):
        # Coordinates which do not share the same unit should fail
        self.a.units = 'kilometer'
        self.assertRaises(ValueError, self.a.intersect, self.b)

    def test_commutative(self):
        cube = iris.tests.stock.realistic_4d()
        coord = cube.coord('grid_longitude')
        offset_coord = coord.copy()
        offset_coord = offset_coord - (offset_coord.points[20] - offset_coord.points[0])
        self.assertEqual(coord.intersect(offset_coord), offset_coord.intersect(coord))


class TestXML(tests.IrisTest):
    def test_minimal(self):
        coord = iris.coords.DimCoord(np.arange(10, dtype=np.int32))
        element = coord.xml_element(Document())
        self.assertXMLElement(coord, ('coord_api', 'minimal.xml'))

    def test_complex(self):
        crs = iris.coord_systems.GeogCS(6370000)
        coord = iris.coords.AuxCoord(np.arange(4, dtype=np.float32),
                                     'air_temperature', 'my_long_name',
                                     units='K',
                                     attributes={'foo': 'bar', 'count': 2},
                                     coord_system=crs)
        coord.guess_bounds(0.5)
        self.assertXMLElement(coord, ('coord_api', 'complex.xml'))


class TestCoord_ReprStr_nontime(tests.IrisTest):
    def setUp(self):
        self.lat = iris.tests.stock.realistic_4d().coord('grid_latitude')[:10]

    def test_DimCoord_repr(self):
        self.assertRepr(self.lat,
                        ('coord_api', 'str_repr', 'dim_nontime_repr.txt'))

    def test_AuxCoord_repr(self):
        self.assertRepr(self.lat,
                        ('coord_api', 'str_repr', 'aux_nontime_repr.txt'))

    def test_DimCoord_str(self):
        self.assertString(str(self.lat),
                          ('coord_api', 'str_repr', 'dim_nontime_str.txt'))

    def test_AuxCoord_str(self):
        self.assertString(str(self.lat),
                          ('coord_api', 'str_repr', 'aux_nontime_str.txt'))


class TestCoord_ReprStr_time(tests.IrisTest):
    def setUp(self):
        self.time = iris.tests.stock.realistic_4d().coord('time')
        
    def test_DimCoord_repr(self):
        self.assertRepr(self.time,
                        ('coord_api', 'str_repr', 'dim_time_repr.txt'))

    def test_AuxCoord_repr(self):
        self.assertRepr(self.time,
                        ('coord_api', 'str_repr', 'aux_time_repr.txt'))

    def test_DimCoord_str(self):
        self.assertString(str(self.time),
                          ('coord_api', 'str_repr', 'dim_time_str.txt'))

    def test_AuxCoord_str(self):
        self.assertString(str(self.time),
                          ('coord_api', 'str_repr', 'aux_time_str.txt'))


class TestAuxCoordCreation(unittest.TestCase):
    def test_basic(self):
        a = iris.coords.AuxCoord(range(10), 'air_temperature', units='kelvin')
        result = "AuxCoord(array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]), standard_name='air_temperature', units=Unit('kelvin'))"
        self.assertEqual(result, str(a))

        b = iris.coords.AuxCoord(range(10), attributes={'monty': 'python'})
        result = "AuxCoord(array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]), standard_name=None, units=Unit('1'), attributes={'monty': 'python'})"
        self.assertEqual(result, str(b))
        
    def test_excluded_attributes(self):
        with self.assertRaises(ValueError):
            iris.coords.AuxCoord(range(10), 'air_temperature', units='kelvin', attributes={'standard_name': 'whoopsy'})
        
        a = iris.coords.AuxCoord(range(10), 'air_temperature', units='kelvin')
        with self.assertRaises(ValueError):
            a.attributes['standard_name'] = 'whoopsy'
        with self.assertRaises(ValueError):
            a.attributes.update({'standard_name': 'whoopsy'})

    def test_coord_system(self):
        a = iris.coords.AuxCoord(range(10), 'air_temperature', units='kelvin', coord_system=iris.coord_systems.GeogCS(6000))
        result = "AuxCoord(array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]), standard_name='air_temperature', units=Unit('kelvin'), "\
                 "coord_system=GeogCS(6000.0))"
        self.assertEqual(result, str(a))
        
    def test_bounded(self):
        a = iris.coords.AuxCoord(range(10), 'air_temperature', units='kelvin', bounds=np.arange(0, 20).reshape(10, 2))
        result = ("AuxCoord(array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])"
                  ", bounds=array([[ 0,  1],\n       [ 2,  3],\n       [ 4,  5],\n       [ 6,  7],\n       [ 8,  9],\n       "\
                  "[10, 11],\n       [12, 13],\n       [14, 15],\n       [16, 17],\n       [18, 19]])"
                  ", standard_name='air_temperature', units=Unit('kelvin'))"
                  )
        self.assertEqual(result, str(a))
        
    def test_string_coord_equality(self):
        b = iris.coords.AuxCoord(['Jan', 'Feb', 'March'], units='no_unit')
        c = iris.coords.AuxCoord(['Jan', 'Feb', 'March'], units='no_unit')
        self.assertEqual(b, c)
  
  
class TestDimCoordCreation(unittest.TestCase):
    def test_basic(self):
        a = iris.coords.DimCoord(range(10), 'air_temperature', units='kelvin')
        result = "DimCoord(array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]), standard_name='air_temperature', units=Unit('kelvin'))"
        self.assertEqual(result, str(a))

        b = iris.coords.DimCoord(range(10), attributes={'monty': 'python'})
        result = "DimCoord(array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]), standard_name=None, units=Unit('1'), attributes={'monty': 'python'})"
        self.assertEqual(result, str(b))
        
    def test_excluded_attributes(self):
        with self.assertRaises(ValueError):
            iris.coords.DimCoord(range(10), 'air_temperature', units='kelvin', attributes={'standard_name': 'whoopsy'})
        
        a = iris.coords.DimCoord(range(10), 'air_temperature', units='kelvin')
        with self.assertRaises(ValueError):
            a.attributes['standard_name'] = 'whoopsy'
        with self.assertRaises(ValueError):
            a.attributes.update({'standard_name': 'whoopsy'})

    def test_coord_system(self):
        a = iris.coords.DimCoord(range(10), 'air_temperature', units='kelvin', coord_system=iris.coord_systems.GeogCS(6000))
        result = "DimCoord(array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]), standard_name='air_temperature', units=Unit('kelvin'), "\
                 "coord_system=GeogCS(6000.0))"
        self.assertEqual(result, str(a))
        
    def test_bounded(self):
        a = iris.coords.DimCoord(range(10), 'air_temperature', units='kelvin', bounds=np.arange(0, 20).reshape(10, 2))
        result = ("DimCoord(array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])"
                  ", bounds=array([[ 0,  1],\n       [ 2,  3],\n       [ 4,  5],\n       [ 6,  7],\n       [ 8,  9],\n       "\
                  "[10, 11],\n       [12, 13],\n       [14, 15],\n       [16, 17],\n       [18, 19]])"
                  ", standard_name='air_temperature', units=Unit('kelvin'))"
                  )
        self.assertEqual(result, str(a))      
        
    def test_dim_coord_restrictions(self):
        # 1d
        with self.assertRaises(ValueError):
            iris.coords.DimCoord([[1,2,3], [4,5,6]]) 
        # monotonic
        with self.assertRaises(ValueError):
            iris.coords.DimCoord([1,2,99,4,5]) 
        # monotonic bounds
        with self.assertRaises(ValueError):
            iris.coords.DimCoord([1,2,3], bounds=[[1, 12], [2, 9], [3, 6]])
        # numeric
        with self.assertRaises(ValueError):
            iris.coords.DimCoord(['Jan', 'Feb', 'March'])
            
    def test_DimCoord_equality(self):
        # basic regular coord
        b = iris.coords.DimCoord([1, 2]) 
        c = iris.coords.DimCoord([1, 2.]) 
        d = iris.coords.DimCoord([1, 2], circular=True)
        self.assertEqual(b, c)
        self.assertNotEqual(b, d)
        
    def test_Dim_to_Aux(self):
        a = iris.coords.DimCoord(range(10), standard_name='air_temperature', long_name='custom air temp',
                                 units='kelvin', attributes={'monty': 'python'}, 
                                 bounds=np.arange(20).reshape(10, 2), circular=True)
        b = iris.coords.AuxCoord.from_coord(a)
        # Note - circular attribute is not a factor in equality comparison
        self.assertEqual(a, b)


class TestCoordMaths(tests.IrisTest):
    def _build_coord(self, start=None, step=None, count=None):
        # Create points and bounds akin to an old RegularCoord.
        dtype = np.float32
        start = dtype(start or self.start)
        step = dtype(step or self.step)
        count = int(count or self.count)
        bound_position = dtype(0.5)
        points = np.arange(count, dtype=dtype) * step + start
        bounds = np.concatenate([[points - bound_position * step], 
                                    [points + (1 - bound_position) * step]]).T
        self.lon = iris.coords.AuxCoord(points, 'latitude',  units='degrees', bounds=bounds)
        self.rlon = iris.coords.AuxCoord(np.deg2rad(points), 'latitude',  units='radians', bounds=np.deg2rad(bounds))

    def setUp(self):
        self.start = 0
        self.step = 2.3
        self.count = 20
        self._build_coord()
        

# TODO - Remove this test class and results files when Coord.cos() and Coord.sin() are removed.
# This class tests two deprecated Coord methods. These methods are now private functions in
# analysis/calculus.py and corresponding tests are in test_analysis_calculus.py.
class TestCoordTrig(TestCoordMaths):    
    def test_sin(self): 
        sin_of_coord = self.lon.sin()
        sin_of_coord_radians = self.rlon.sin()
        
        # Check the values are correct (within a tolerance)
        np.testing.assert_array_almost_equal(np.sin(self.rlon.points), sin_of_coord.points)
        np.testing.assert_array_almost_equal(np.sin(self.rlon.bounds), sin_of_coord.bounds)
        
        # Check that the results of the sin function are almost equal when operating on a coord with degrees and radians
        np.testing.assert_array_almost_equal(sin_of_coord.points, sin_of_coord_radians.points)
        np.testing.assert_array_almost_equal(sin_of_coord.bounds, sin_of_coord_radians.bounds)
        
        self.assertEqual(sin_of_coord.name(), 'sin(latitude)')
        self.assertEqual(sin_of_coord.units, '1')
        
    def test_cos(self):
        cos_of_coord = self.lon.cos()
        cos_of_coord_radians = self.rlon.cos()
        
        # Check the values are correct (within a tolerance)
        np.testing.assert_array_almost_equal(np.cos(self.rlon.points), cos_of_coord.points)
        np.testing.assert_array_almost_equal(np.cos(self.rlon.bounds), cos_of_coord.bounds)
        
        # Check that the results of the cos function are almost equal when operating on a coord with degrees and radians
        np.testing.assert_array_almost_equal(cos_of_coord.points, cos_of_coord_radians.points)
        np.testing.assert_array_almost_equal(cos_of_coord.bounds, cos_of_coord_radians.bounds)
        
        # now that we have tested the points & bounds, remove them and just test the xml
        cos_of_coord._points = np.array([1], dtype=np.float32)
        cos_of_coord._bounds = None
        cos_of_coord_radians._points = np.array([1], dtype=np.float32)
        cos_of_coord_radians._bounds = None

        self.assertXMLElement(cos_of_coord, ('coord_api', 'coord_maths', 'cos_simple.xml'))
        self.assertXMLElement(cos_of_coord_radians, ('coord_api', 'coord_maths', 'cos_simple_radians.xml'))
                
    
class TestCoordAdditionSubtract(TestCoordMaths):
    def test_subtract(self):
        r_expl = self.lon - 10
        self.assertXMLElement(r_expl, ('coord_api', 'coord_maths', 'subtract_simple_expl.xml'))
        
    def test_subtract_in_place(self):
        r_expl = self.lon.copy()
        r_expl -= 10
        self.assertXMLElement(r_expl, ('coord_api', 'coord_maths', 'subtract_simple_expl.xml'))
        
    def test_neg(self):
        self._build_coord(start=8)
        r_expl = -self.lon
        np.testing.assert_array_equal(r_expl.points, -(self.lon.points))
        self.assertXMLElement(r_expl, ('coord_api', 'coord_maths', 'negate_expl.xml'))
        
    def test_right_subtract(self):
        r_expl = 10 - self.lon
        # XXX original xml was for regular case, not explicit.
        self.assertXMLElement(r_expl, ('coord_api', 'coord_maths', 'r_subtract_simple_exl.xml'))
        
    def test_add(self):
        r_expl = self.lon + 10
        self.assertXMLElement(r_expl, ('coord_api', 'coord_maths', 'add_simple_expl.xml'))
        
    def test_add_in_place(self):
        r_expl = self.lon.copy()
        r_expl += 10
        self.assertXMLElement(r_expl, ('coord_api', 'coord_maths', 'add_simple_expl.xml'))
        
    def test_add_float(self):
        r_expl = self.lon + 10.321
        self.assertXMLElement(r_expl, ('coord_api', 'coord_maths', 'add_float_expl.xml'))
        self.assertEqual(r_expl, 10.321 + self.lon.copy() )
        
        
class TestCoordMultDivide(TestCoordMaths):
    def test_divide(self):
        r_expl = self.lon.copy() / 10
        self.assertXMLElement(r_expl, ('coord_api', 'coord_maths', 'divide_simple_expl.xml'))
        
    def test_right_divide(self):
        self._build_coord(start=10)
        test_coord = self.lon.copy()
        
        r_expl = 1 / test_coord
        self.assertXMLElement(r_expl, ('coord_api', 'coord_maths', 'right_divide_simple_expl.xml'))

    def test_divide_in_place(self):
        r_expl = self.lon.copy()
        r_expl /= 10
        self.assertXMLElement(r_expl, ('coord_api', 'coord_maths', 'divide_simple_expl.xml'))
        
    def test_multiply(self):
        r_expl = self.lon.copy() * 10
        self.assertXMLElement(r_expl, ('coord_api', 'coord_maths', 'multiply_simple_expl.xml'))
        
    def test_multiply_in_place_reg(self):
        r_expl = self.lon.copy()
        r_expl *= 10
        self.assertXMLElement(r_expl, ('coord_api', 'coord_maths', 'multiply_simple_expl.xml'))
        
    def test_multiply_float(self):
        r_expl = self.lon.copy() * 10.321
        self.assertXMLElement(r_expl, ('coord_api', 'coord_maths', 'mult_float_expl.xml'))
        self.assertEqual(r_expl, 10.321 * self.lon.copy() )
        

class TestCoordCollapsed(tests.IrisTest):
    def create_1d_coord(self, bounds=None, points=None, units='meter'):
        coord = iris.coords.DimCoord(points, long_name='test', units=units, 
                                     bounds=bounds)
        return coord
        
    def test_explicit(self):
        orig_coord = self.create_1d_coord(points=range(10), 
                                          bounds=[(b, b+1) for b in range(10)])
        coord_expected = self.create_1d_coord(points=5, bounds=[(0, 10)])

        # test points & bounds
        self.assertEqual(coord_expected, orig_coord.collapsed())
        
        # test points only
        coord = orig_coord.copy()
        coord_expected = self.create_1d_coord(points=4, bounds=[(0, 9)])
        coord.bounds = None
        self.assertEqual(coord_expected, coord.collapsed())        

    def test_circular_collapse(self):
        # set up a coordinate that wraps 360 degrees in points using the circular flag
        coord = self.create_1d_coord(None, np.arange(10) * 36, 'degrees')
        expected_coord = self.create_1d_coord([0., 360.], [180.], 'degrees')
        coord.circular = True
        
        # test collapsing
        self.assertEqual(expected_coord, coord.collapsed())
        # the order of the points/bounds should not affect the resultant bounded coordinate 
        coord = coord[::-1]
        self.assertEqual(expected_coord, coord.collapsed())
        
    def test_nd_bounds(self):
        cube = iris.tests.stock.simple_2d_w_multidim_coords(with_bounds=True)
        pcube = cube.collapsed(['bar','foo'], iris.analysis.SUM)
        pcube.data = pcube.data.astype('i8')
        self.assertCML(pcube, ("coord_api", "nd_bounds.cml"))


class TestGetterSetter(tests.IrisTest):
    def test_get_set_points_and_bounds(self):
        cube = iris.tests.stock.realistic_4d()
        coord = cube.coord("grid_latitude")
        
        # get bounds
        bounds = coord.bounds
        self.assertEquals(bounds.shape, (100, 2))
        
        self.assertEqual(bounds.shape[-1], coord.nbounds)
        
        # set bounds
        coord.bounds = bounds + 1
        
        np.testing.assert_array_equal(coord.bounds, bounds + 1)

        # set bounds - different length to existing points
        with self.assertRaises(ValueError):
            coord.bounds = bounds[::2, :]
        
        # set points/bounds to None
        with self.assertRaises(ValueError):
            coord.points = None
        coord.bounds = None
        
        # set bounds from non-numpy pair
        coord._points = None  # reset the undelying shape of the coordinate
        coord.points = 1
        coord.bounds = [123, 456]
        self.assertEqual(coord.shape, (1, ))
        self.assertEqual(coord.bounds.shape, (1, 2))
        
        # set bounds from non-numpy pairs
        coord._points = None # reset the undelying shape of the coordinate
        coord.points = range(3)
        coord.bounds = [[123, 456], [234, 567], [345, 678]]
        self.assertEqual(coord.shape, (3, ))
        self.assertEqual(coord.bounds.shape, (3, 2))
        

class TestGuessBounds(tests.IrisTest):
    def test_guess_bounds(self):
        coord = iris.coords.DimCoord(np.array([0, 10, 20, 30]), long_name="foo", units="1")
        coord.guess_bounds()
        self.assertArrayEqual(coord.bounds, np.array([[-5,5], [5,15], [15,25], [25,35]]))
        
        coord.bounds = None
        coord.guess_bounds(0.25)
        self.assertArrayEqual(coord.bounds, np.array([[-5,5], [5,15], [15,25], [25,35]]) + 2.5)
        
        coord.bounds = None
        coord.guess_bounds(0.75)
        self.assertArrayEqual(coord.bounds, np.array([[-5,5], [5,15], [15,25], [25,35]]) - 2.5)

        points = coord.points.copy()
        points[2] = 25
        coord.points = points
        coord.bounds = None
        coord.guess_bounds()
        self.assertArrayEqual(coord.bounds, np.array([[-5.,5.], [5.,17.5], [17.5,27.5], [27.5,32.5]]))
        
        # if the points are not monotonic, then guess_bounds should fail
        points[2] = 32
        coord = iris.coords.AuxCoord.from_coord(coord)
        coord.points = points
        coord.bounds = None
        with self.assertRaises(ValueError):
            coord.guess_bounds()


class TestCoordCompatibility(tests.IrisTest):
    def setUp(self):
        self.aux_coord = iris.coords.AuxCoord([1., 2. ,3.],
                                              standard_name='longitude',
                                              var_name='lon',
                                              units='degrees')
        self.dim_coord = iris.coords.DimCoord(np.arange(0, 360, dtype=np.float64),
                                              standard_name='longitude',
                                              var_name='lon',
                                              units='degrees',
                                              circular=True)

    def test_not_compatible(self):
        r = self.aux_coord.copy()
        self.assertTrue(self.aux_coord.is_compatible(r))
        # The following changes should make the coords incompatible.
        # Different units.
        r.units = 'radians'
        self.assertFalse(self.aux_coord.is_compatible(r))
        # Different coord_systems.
        r = self.aux_coord.copy()
        r.coord_system = iris.coord_systems.GeogCS(6371229)
        self.assertFalse(self.aux_coord.is_compatible(r))
        # Different attributes.
        r = self.aux_coord.copy()
        self.aux_coord.attributes['source']= 'bob'
        r.attributes['source'] = 'alice'
        self.assertFalse(self.aux_coord.is_compatible(r))

    def test_compatible(self):
        # The following changes should not affect compatibility.
        # Different non-common attributes.
        r = self.aux_coord.copy()
        self.aux_coord.attributes['source']= 'bob'
        r.attributes['origin'] = 'alice'
        self.assertTrue(self.aux_coord.is_compatible(r))
        # Different points.
        r.points = np.zeros(r.points.shape)
        self.assertTrue(self.aux_coord.is_compatible(r))
        # Different var_names (but equal name()).
        r.var_name = 'foo'
        self.assertTrue(self.aux_coord.is_compatible(r))
        # With/without bounds.
        r.bounds = np.array([[0.5, 1.5],[1.5, 2.5],[2.5, 3.5]])
        self.assertTrue(self.aux_coord.is_compatible(r))

    def test_circular(self):
        # Test that circular has no effect on compatibility.
        # AuxCoord and circular DimCoord.
        self.assertTrue(self.aux_coord.is_compatible(self.dim_coord))
        # circular and non-circular DimCoord.
        r = self.dim_coord.copy()
        r.circular = False
        self.assertTrue(r.is_compatible(self.dim_coord))

    def test_defn(self):
        coord_defn = self.aux_coord._as_defn()
        self.assertTrue(self.aux_coord.is_compatible(coord_defn))
        coord_defn = self.dim_coord._as_defn()
        self.assertTrue(self.dim_coord.is_compatible(coord_defn))

    def test_is_ignore(self):
        r = self.aux_coord.copy()
        self.aux_coord.attributes['source']= 'bob'
        r.attributes['source'] = 'alice'
        self.assertFalse(self.aux_coord.is_compatible(r))
        # Use ignore keyword.
        self.assertTrue(self.aux_coord.is_compatible(r, ignore='source'))
        self.assertTrue(self.aux_coord.is_compatible(r, ignore=('source',)))
        self.assertTrue(self.aux_coord.is_compatible(r, ignore=r.attributes))


if __name__ == "__main__":
    tests.main()
