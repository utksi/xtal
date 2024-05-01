"""
Module for generating atomic crystals
"""

# Standard Libraries
import random
from copy import deepcopy
import numpy as np

# PyXtal imports #avoid *
from pyxtal.symmetry import Group, choose_wyckoff
from pyxtal.wyckoff_site import atom_site
from pyxtal.msg import Comp_CompatibilityError, VolumeError
from pyxtal.tolerance import Tol_matrix
from pyxtal.lattice import Lattice
from pyxtal.database.element import Element

# Define functions
# ------------------------------
class random_crystal:
    """
    Class for storing and generating atomic crystals based on symmetry
    constraints. Given a spacegroup, list of atomic symbols, the stoichiometry,
    and a volume factor, generates a random crystal consistent with the
    spacegroup's symmetry.

    Args:
        dim: dimenion (0, 1, 2, 3)
        group: the group number (1-56, 1-75, 1-80, 1-230)
        species: a list of atomic symbols for each ion type, e.g., `["Ti", "O"]`
        numIons: a list of the number of each type of atom within the
            primitive cell (NOT the conventional cell), e.g., `[4, 2]`
        factor (optional): volume factor used to generate the crystal
        sites (optional): pre-assigned wyckoff sites (e.g., `[["4a"], ["2b"]]`)
        lattice (optional): `Lattice <pyxtal.lattice.Lattice.html>`_ object to
            define the unit cell
        tm (optional): `Tol_matrix <pyxtal.tolerance.Tol_matrix.html>`_ object
            to define the distances
    """

    def __init__(
        self,
        dim = 3,
        group = 227,
        species = ['C'],
        numIons = 8,
        factor = 1.1,
        thickness = None,
        area = None,
        lattice = None,
        sites = None,
        conventional = True,
        tm = Tol_matrix(prototype="atomic"),
        use_hall = False):

        # Initialize
        self.source = 'Random'
        self.valid = False
        self.factor = factor
        self.min_density = 0.75

        # Dimesion
        self.dim = dim
        self.area = area  # Cross-section area for 1D
        self.thickness = thickness # Thickness of 2D slab
        self.lattice0 = lattice

        #The periodic boundary condition
        if dim == 3:
            self.PBC = [1, 1, 1]
        elif dim == 2:
            self.PBC = [1, 1, 0]
        elif dim == 1:
            self.PBC = [0, 0, 1]
        elif dim == 0:
            self.PBC = [0, 0, 0]

        # Symmetry group
        if type(group) == Group:
            self.group = group
        else:
            self.group = Group(group, dim=self.dim, use_hall=use_hall)
        self.number = self.group.number
        self.symbol = self.group.symbol

        # Composition
        numIons = np.array(numIons)
        if not conventional:
            mul = self.group.cellsize()
        else:
            mul = 1
        self.numIons = numIons * mul
        self.species = species

        # Tolerance matrix
        if type(tm) == Tol_matrix:
            self.tol_matrix = tm
        else:
            self.tol_matrix = Tol_matrix(prototype=tm)
        # Wyckoff sites
        self.set_sites(sites)

        # Lattice and coordinates
        compat, self.degrees = self.group.check_compatible(self.numIons)
        if not compat:
            self.valid = False
            msg = "Compoisition " + str(self.numIons)
            msg += " not compatible with symmetry "
            msg += str(self.group.number)
            raise Comp_CompatibilityError(msg)
        else:
            #self.set_volume()
            #self.set_lattice(self.lattice0)
            self.set_elemental_volumes()
            self.set_crystal()

    def __str__(self):
        if self.valid:
            s = "------Crystal from {:s}------".format(self.source)
            s += "\nDimension: {}".format(self.dim)
            s += "\nGroup: {} ({})".format(self.symbol, self.number)
            s += "\n{}".format(self.lattice)
            s += "\nWyckoff sites:"
            for wyc in self.atom_sites:
                s += "\n\t{}".format(wyc)
        else:
            s = "\nStructure not available."
        return s

    def __repr__(self):
        return str(self)

    def set_sites(self, sites):
        """
        initialize Wyckoff sites
        Update 2023/09, track the wp index instead of letters to
        avoid many inquiries
        Args:
            sites: list
        """
        # Symmetry sites
        self.sites = {}
        for i, specie in enumerate(self.species):
            if sites is not None and sites[i] is not None and len(sites[i])>0:
                self.sites[specie] = []
                self._check_consistency(sites[i], self.numIons[i])

                if type(sites[i]) is dict:
                    for item in sites[i].items():
                        # keep the record of wp index
                        id = self.group.get_index_by_letter(item[0])
                        self.sites[specie].append((id, item[1]))
                elif type(sites[i]) is list: #tuple
                    for site in sites[i]:
                        if type(site) is tuple:
                            (letter, x, y, z) = site
                            id = self.group.get_index_by_letter(letter)
                            self.sites[specie].append((id, (x, y, z)))
                        else:
                            id = self.group.get_index_by_letter(site)
                            self.sites[specie].append(id)
            else:
                self.sites[specie] = None

    def set_elemental_volumes(self):
        """
        set up the radii for each specie
        """
        self.elemental_volumes = []
        for specie in self.species:
            sp = Element(specie)
            vol1, vol2 = sp.covalent_radius ** 3, sp.vdw_radius ** 3
            self.elemental_volumes.append([4/3*np.pi*vol1, 4/3*np.pi*vol2])

    def set_volume(self):
        """
        Estimates the volume of a unit cell based on the number/types of ions.
        Assumes each atom takes up a sphere with radius equal to its covalent
        bond radius.
        0.50 A -> 0.52 A^3
        0.62 A -> 1.00 A^3
        0.75 A -> 1.76 A^3

        Returns:
            a float value for the estimated volume
        """
        volume = 0
        for i, numIon in enumerate(self.numIons):
            [vmin, vmax] = self.elemental_volumes[i]
            volume += numIon * random.uniform(vmin, vmax)
        self.volume = self.factor * volume

        #make sure the volume is not too small
        if self.volume/sum(self.numIons) < self.min_density:
            self.volume = sum(self.numIons) * self.min_density

    def set_lattice(self, lattice):
        """
        Generate the initial lattice
        """
        if lattice is not None:
            # Use the provided lattice
            self.lattice = lattice
            self.volume = lattice.volume
            # Make sure the custom lattice PBC axes are correct.
            if lattice.PBC != self.PBC:
                self.lattice.PBC = self.PBC
        else:
            # Determine the unique axis
            if self.dim == 2:
                if self.number in range(3, 8):
                    unique_axis = "c"
                else:
                    unique_axis = "a"
            elif self.dim == 1:
                if self.number in range(3, 8):
                    unique_axis = "a"
                else:
                    unique_axis = "c"
            else:
                unique_axis = "c"

            # Generate a Lattice instance
            good_lattice = False
            for cycle in range(10):
                try:
                    self.lattice = Lattice(
                        self.group.lattice_type,
                        self.volume,
                        PBC=self.PBC,
                        unique_axis=unique_axis,
                        thickness=self.thickness,
                        area=self.area,
                        )
                    good_lattice = True
                    break
                except VolumeError:
                    self.volume *= 1.1
                    msg = "Warning: increase the volume by 1.1 times: "
                    msg += "{:.2f}".format(self.volume)
                    print(msg)

            if not good_lattice:
                msg = "Volume estimation {:.2f} is very bad".format(self.volume)
                msg += " with the given composition "
                msg += str(self.numIons)
                raise RuntimeError(msg)

    def set_crystal(self):
        """
        The main code to generate a random atomic crystal.
        If successful, `self.valid` is True
       """
        self.numattempts = 0
        if not self.degrees:
            self.lattice_attempts = 5
            self.coord_attempts = 5
        else:
            self.lattice_attempts = 40
            self.coord_attempts = 10
        
        #QZ: Maybe we no longer need this tag
        #if not self.lattice.allow_volume_reset:
        #    self.lattice_attempts = 1

        for cycle1 in range(self.lattice_attempts):
            self.set_volume()
            self.set_lattice(self.lattice0)
            #print("VOLUME", cycle1, self.volume)
            self.cycle1 = cycle1
            for cycle2 in range(self.coord_attempts):
                self.cycle2 = cycle2
                output = self._set_coords()

                if output:
                    self.atom_sites = output
                    break
            if self.valid:
                return
            else:
                self.lattice.reset_matrix()

        return

    def _set_coords(self):
        """
        generate coordinates for random crystal
        """
        wyks = []
        cell = self.lattice.matrix
        # generate coordinates for each ion type in turn
        for numIon, specie in zip(self.numIons, self.species):
            output = self._set_ion_wyckoffs(numIon, specie, cell, wyks)
            if output is not None:
                wyks.extend(output)
            else:
                # correct multiplicity not achieved exit and start over
                return None

        # If numIon_added correct for all specie return structure
        self.valid = True
        return wyks

    def _set_ion_wyckoffs(self, numIon, specie, cell, wyks):
        """
        generates a set of wyckoff positions to accomodate a given number
        of ions

        Args:
            numIon: Number of ions to accomodate
            specie: Type of species being placed on wyckoff site
            cellx: Matrix of lattice vectors
            wyks: current wyckoff sites

        Returns:
            Sucess:
                wyckoff_sites_tmp: list of wyckoff sites for valid sites
            Failue:
                None

        """
        numIon_added = 0
        tol = self.tol_matrix.get_tol(specie, specie)
        wyckoff_sites_tmp = []

        # Now we start to add the specie to the wyckoff position
        sites_list = deepcopy(self.sites[specie]) # the list of Wyckoff site
        if sites_list is not None:
            wyckoff_attempts = max(len(sites_list)*2, 10)
        else:
            # the minimum numattempts is to put all atoms to the general WPs
            min_wyckoffs = int(numIon/len(self.group.wyckoffs_organized[0][0]))
            wyckoff_attempts = max(2*min_wyckoffs, 10)

        cycle = 0
        while cycle < wyckoff_attempts:
            # Choose a random WP for given multiplicity: 2a, 2b
            if sites_list is not None and len(sites_list)>0:
                site = sites_list[0]
            else: # Selecting the merging
                site = None

            new_site = None
            if type(site) is tuple: #site with coordinates
                #print(site)
                (index, xyz) = site
                wp = self.group[index]
                new_site = atom_site(wp, xyz, specie)
            else:
                if site is not None:
                    wp = self.group[site]
                    pt = self.lattice.generate_point()
                    # avoid using the merge function
                    if len(wp.short_distances(pt, cell, tol)) > 0:
                        #print('bad pt', pt, wp.short_distances(pt, cell, tol))
                        cycle += 1
                        continue
                    else:
                        # update pt
                        pt = wp.project(pt, cell, self.PBC)
                        #print('good', pt, tol, len(wp.short_distances(pt, cell, tol)))
                else:
                    # generate wp
                    wp = choose_wyckoff(self.group, numIon-numIon_added, site, self.dim)
                    if wp is not False:
                        #print(wp.letter)
                        passed_wp_check = True
                        # Generate a list of coords from ops
                        pt = self.lattice.generate_point()
                        pt, wp, _ = wp.merge(pt, cell, tol, group=self.group)
                #print('good pt', pt)  
                if wp is not False:
                    # For pure planar structure
                    if self.dim == 2 and self.thickness is not None and \
                        self.thickness < 0.1:
                        pt[-1] = 0.5
                    new_site = atom_site(wp, pt, specie)

            # Check current WP against existing WP's
            if self.check_wp(wyckoff_sites_tmp, wyks, cell, new_site):
                if sites_list is not None and len(sites_list)>0:
                    sites_list.pop(0)
                wyckoff_sites_tmp.append(new_site)
                numIon_added += new_site.multiplicity

                # Check if enough atoms have been added
                if numIon_added == numIon:
                    return wyckoff_sites_tmp

            cycle += 1
            self.numattempts += 1

        return None

    def check_wp(self, wyckoff_sites_tmp, wyks, cell, new_site):
        # Check current WP against existing WP's
        if new_site is None:
            return False

        for ws in wyckoff_sites_tmp + wyks:
            if not new_site.check_with_ws2(ws, cell, self.tol_matrix):
                return False
        return True


    def _check_consistency(self, site, numIon):
        num = 0
        for s in site:
            if type(s) is dict:
                for key in s.keys():
                    num += int(key[:-1])
            else:
                num += int(s[:-1])
        if numIon == num:
            return True
        else:
            diff = numIon - num
            if diff > 0:
                #check if compatible
                compat, self.degrees = self.group.check_compatible([diff])
                if compat:
                    return True
                else:
                    msg = "\nfrom numIons: {:d}".format(numIon)
                    msg += "\nfrom Wyckoff list: {:d}".format(num)
                    msg += "\nThe number is incompatible with composition: "
                    mse += str(site)
                raise ValueError(msg)
            else:
                msg = "\nfrom numIons: {:d}".format(numIon)
                msg += "\nfrom Wyckoff list: {:d}".format(num)
                msg += "\nThe requested number is greater than composition: "
                msg += str(site)
                raise ValueError(msg)
