r"""
Flat veering triangulations.

Note:

- when graphviz generates a svg it specifies a given size with the
  attributes "width" and "height". This would better be redefined
  to width="100%".
"""

import math

from sage.structure.sequence import Sequence

from sage.categories.fields import Fields

from sage.rings.all import ZZ, QQ, AA, RDF, NumberField
from sage.rings.polynomial.polynomial_ring_constructor import PolynomialRing

from sage.modules.free_module import VectorSpace
from sage.modules.free_module_element import vector

from sage.misc.prandom import shuffle
from sage.plot.graphics import Graphics
from sage.plot.line import line2d
from sage.plot.polygon import polygon2d
from sage.plot.text import text
from sage.plot.bezier_path import bezier_path
from sage.plot.point import point2d

from .constants import BLUE, RED, PURPLE, GREEN, HORIZONTAL, VERTICAL
from .misc import flipper_nf_to_sage, flipper_nf_element_to_sage, det2
from .triangulation import Triangulation
from .veering_triangulation import VeeringTriangulation

QQx = PolynomialRing(QQ, 'x')
_Fields = Fields()

EDGE_COLORS = {
    BLUE: 'blue',
    RED: 'red',
    PURPLE: 'purple',
    GREEN: 'green'
    }


def flipper_edge(T, e):
    r"""
    EXAMPLES::

        sage: import flipper
        sage: from veerer.layout import flipper_edge

        sage: T = flipper.create_triangulation([(0r,1r,2r),(-1r,-2r,-3r)])
        sage: sorted([flipper_edge(T, e) for e in T.edges])
        [0, 1, 2, 3, 4, 5]
    """
    n = (3 * T.num_triangles)
    e = e.label
    return n * (e < 0) + e

def flipper_edge_perm(n):
    from array import array
    return array('l', range(n-1,-1,-1))

def vec_slope(v):
    r"""
    Return the slope of a 2d vector ``v``.

    EXAMPLES::

        sage: from veerer.constants import RED, BLUE, PURPLE, GREEN
        sage: from veerer.layout import vec_slope

        sage: vec_slope((1,0)) == PURPLE
        True
        sage: vec_slope((0,1)) == GREEN
        True
        sage: vec_slope((1,1)) == vec_slope((-1,-1)) == RED
        True
        sage: vec_slope((1,-1)) == vec_slope((1,-1)) == BLUE
        True
    """
    if v[0].is_zero():
        return GREEN
    elif v[1].is_zero():
        return PURPLE
    elif v[0] * v[1] > 0:
        return RED
    else:
        return BLUE


def has_intersection(triangles, new_triangle, pos):
    r"""
    Check whether ``new_triangle`` intersects one of the triangles in ``triangles``
    where the positions of the vertices have to be found in ``pos``.
    """
    for t in triangles:
        for i in range(3):
            p1 = t[i]
            p2 = t[(i+1)%3]
            for j in range(3):
                q1 = new_triangle[j]
                q2 = new_triangle[(j+1)%3]

                if (orientation(p1,p2,q1) != orientation(p1,p2,q2) and \
                    orientation(q1,q2,p1) != orientation(q1,q2,p2)):
                    return True

    return False

# TODO:
# class FlatVeeringTriangulation(VeeringTriangulation)
# in this class we do not choose the color after a flip.
# it is entierly determined by the slopes of the vectors.

class FlatVeeringTriangulationLayout:
    r"""
    A flat triangulation.

    EXAMPLES:

        sage: from veerer import *

    A flat triangulation can either be built from a list of triangles and
    vectors::

        sage: triangles = [(0, 1, 2), (-1, -2, -3)]
        sage: vecs = [(1, 2), (-2, -1), (1, -1), (1, -1), (-2, -1), (1, 2)]
        sage: FlatVeeringTriangulationLayout(triangles, vecs)
        Flat Triangulation made of 2 triangles

    Or a coloured triangulation (in that situation the "smallest" integral
    solution is picked)::

        sage: T = VeeringTriangulation("(0,1,2)(~0,~1,3)", "BRBB")
        sage: FlatVeeringTriangulationLayout.from_coloured_triangulation(T)
        Flat Triangulation made of 2 triangles

    Or a pseudo-Anosov homeomorphism from flipper::

        sage: from flipper import *

        sage: T = flipper.load('S_2_1')
        sage: h = T.mapping_class('abCeF')
        sage: FlatVeeringTriangulationLayout.from_pseudo_anosov(h)
        Flat Triangulation made of 12 triangles
    """
    def __init__(self, triangles, vectors,
            blue_cylinders=None, red_cylinders=None):
        r"""
        INPUT:

        - triangles - a triangulation

        - vectors - a list of 2n vectors

        - ``blue_cylinders`` and ``red_cylinders`` - optional list of edges
        """
        if isinstance(triangles, Triangulation):
            self._triangulation = triangles.copy()
        else:
            self._triangulation = Triangulation(triangles)

        n = self._triangulation.num_half_edges()
        m = self._triangulation.num_edges()

        if len(vectors) == m:
            ep = self._triangulation._ep
            for e in range(m):
                E = ep[e]
                if e != E and E < m:
                    raise ValueError("edge perm not in standard form")
            vectors = vectors + [vectors[ep[e]] for e in range(m,n)]
        if len(vectors) != n:
            raise ValueError('wrong number of vectors')

        vectors = Sequence([vector(v) for v in vectors])
        self._V = vectors.universe()
        self._K = self._V.base_ring()

        if self._K not in _Fields:
            self._K = self._K.fraction_field()
            self._V = self._V.change_ring(self._K)
            vectors = [v.change_ring(self._K) for v in vectors]

        self._vectors = list(vectors)        # edge vectors     (list of length n)

        cols = [vec_slope(self._vectors[e]) for e in range(n)]
        self._triangulation = VeeringTriangulation(self._triangulation, cols)

        # for actual display
        self._pos = None                     # vertex positions (list of length n)

        self._check()

    def _check(self):
        r"""
        EXAMPLES::

            sage: from veerer import *
            sage: T = VeeringTriangulation("(0,1,2)(~0,~1,3)", "BRRR")
            sage: assert T.is_core()
            sage: F = T.flat_structure_min()
            sage: F.set_pos()
            sage: F._check()
        """
        self._triangulation._check()

        n = self._triangulation.num_half_edges()
        ep = self._triangulation._ep
        for a in range(n):
            A = ep[a]
            u = self._vectors[a]
            v = self._vectors[A]
            if u != v and u != -v:
                raise ValueError('ep[%s] = %s but vec[%s] = %s' % (a, u, A, v))

        vectors = self._vectors
        for a,b,c in self._triangulation.faces():
            va = vectors[a]
            vb = vectors[b]
            vc = vectors[c]
            if va + vb + vc:
                raise ValueError('vec[%s] = %s, vec[%s] = %s and vec[%s] = %s do not sum to zero' % (a, va, b, vb, c, vc))

            if det2(va, vb) <= 0 or det2(vb, vc) <= 0 or det2(vc, va) <= 0:
                raise ValueError('(%s, %s, %s) is a clockwise triangle' %
                        (a, b, c))

        pos = self._pos
        if pos is not None:
            for a,b,c in self._triangulation.faces():
                if pos[a] + vectors[a] != pos[b] or \
                   pos[b] + vectors[b] != pos[c] or \
                   pos[c] + vectors[c] != pos[a]:
                    raise ValueError('pos[%s] = %s, pos[%s] = %s, pos[%s] = %s while vec[%s] = %s, vec[%s] = %s, vec[%s] = %s' % (
                                   a, pos[a],
                                   b, pos[b],
                                   c, pos[c],
                                   a, vectors[a],
                                   b, vectors[b],
                                   c, vectors[c]))

    @classmethod
    def from_pseudo_anosov(cls, h):
        r"""
        Construct the flat structure from a pseudo-Anosov homeomorphism.

        EXAMPLES::

            sage: from flipper import *
            sage: from veerer import *

            sage: T = flipper.load('SB_4')
            sage: h = T.mapping_class('s_0S_1s_2S_3s_1S_2')
            sage: FlatVeeringTriangulationLayout.from_pseudo_anosov(h)
            Flat Triangulation made of 4 triangles
        """
        from permutation import perm_init
        Fh = h.flat_structure()
        Th = Fh.triangulation
        n = 3 * Th.num_triangles # number of half edges

        # extract triangulation
        triangles = [(flipper_edge(Th, e), flipper_edge(Th, f), flipper_edge(Th, g)) for e,f,g in Th]
        fp = perm_init(triangles)
        ep = flipper_edge_perm(n)
        T = Triangulation.from_face_edge_perms(fp, ep)

        # extract flat structure
        x = Fh.edge_vectors.values()[0].x
        K = flipper_nf_to_sage(x.number_field)
        V = VectorSpace(K, 2)
        # translate into Sage number field
        Vec = {flipper_edge(Th,e): V((flipper_nf_element_to_sage(v.x, K),
                               flipper_nf_element_to_sage(v.y, K)))
                  for e,v in Fh.edge_vectors.items()}
        vectors = [Vec[i] for i in range(n)]

        return FlatVeeringTriangulationLayout(T, vectors)

    @classmethod
    def from_coloured_triangulation(cls, T):
        r"""
        Construct a flat triangulation associated to a given coloured triangulation.

        EXAMPLES::

            sage: from veerer import *

            sage: T = VeeringTriangulation([(0,1,2), (-1,-2,-3)], [RED, RED, BLUE])
            sage: FlatVeeringTriangulationLayout.from_coloured_triangulation(T)
            Flat Triangulation made of 2 triangles
        """
        return T.flat_structure_min()

    def xy_scaling(self, sx, sy):
        r"""
        Apply Teichmueller flow to actually see things.
        """
        for i,v in enumerate(self._vectors):
            self._vectors[i] = self._V((sx*v[0], sy*v[1]))

    def _edge_slope(self, e):
        return vec_slope(self._vectors[e])

    def __repr__(self):
        return 'Flat Triangulation made of %s triangles' % self._triangulation.num_faces()

    def set_pos(self, cylinders=None, y_space=0.1):
        r"""
        Set position randomly.

        INPUT:

        - ``cylinders`` - an optional list of cylinders

        EXAMPLES::

            sage: from veerer import *

            sage: T = VeeringTriangulation("(0,1,2)(~0,~1,~2)", "BBR")
            sage: F = T.flat_structure_min(allow_degenerations=True)
            sage: F.set_pos(cylinders=T.cylinders(BLUE) + T.cylinders(RED))
            sage: F.plot()
            Graphics object consisting of 13 graphics primitives
        """
        n = self._triangulation.num_half_edges()
        half_edge_to_face = [None] * n
        faces = self._triangulation.faces()

        for i,(e0,e1,e2) in enumerate(faces):
            half_edge_to_face[e0] = i
            half_edge_to_face[e1] = i
            half_edge_to_face[e2] = i

        nf = self._triangulation.num_faces()
        face_seen = [False] * nf
        fp = self._triangulation.face_permutation(copy=False)
        ep = self._triangulation.edge_permutation(copy=False)
        vectors = self._vectors
        pos = self._pos = [None] * (3*nf)

        y = 0   # current height

        # set the cylinders
        if cylinders:
            for cyl in cylinders:
                xmin = xmax = ymin = ymax = self._K.zero()
                a = cyl[0]
                pos[a] = self._V((0,0))

                for e in cyl:
                    a = ep[e]
                    b = fp[a]
                    c = fp[b]
                    face_seen[half_edge_to_face[a]] = True
#                    print(' -- %s --> (%s, %s, %s)' % (edge_label(e), edge_label(a),
#                         edge_label(b), edge_label(c)))

                    if vectors[a] == vectors[e]:
                        vectors[a] *= -1
                        vectors[b] *= -1
                        vectors[c] *= -1

                    pos[a] = pos[e] + vectors[e]
                    pos[b] = pos[a] + vectors[a]
                    pos[c] = pos[b] + vectors[b]
                    xmin = min(xmin, pos[a][0], pos[b][0], pos[c][0])
                    xmax = max(xmax, pos[a][0], pos[b][0], pos[c][0])
                    ymin = min(ymin, pos[a][1], pos[b][1], pos[c][1])
                    ymax = max(ymax, pos[a][1], pos[b][1], pos[c][1])

                # 2. translate positions according to bounding box
                #    and the current height position
                t = self._V((-xmin, y-ymin))
                for e in cyl:
                    a = ep[e]
                    b = fp[a]
                    c = fp[b]
                    pos[a] += t
                    pos[b] += t
                    pos[c] += t

                # 3. set new starting height
                y += ymax - ymin + y_space

        n = self._triangulation.num_half_edges()
        for e in range(n):
            f = half_edge_to_face[e]
            if (pos[e] is None) != (face_seen[half_edge_to_face[e]] is False):
                a,b,c = faces[f]
                raise RuntimeError('cylinder badly set: pos[%s] = %s while its face (%s,%s,%s) is %s' % (e, self._pos[e], a, b, c, 'seen' if face_seen[half_edge_to_face[e]] else 'unseen'))

        # random forest
        while any(x is False for x in face_seen):
            # choose a starting face
            for start in range(nf):
                if face_seen[start] is False:
                    break

#            print('new root: {}'.format(edge_label(start)))

            # sets its position
            a, b, c = faces[start]
            pos[a] = self._V.zero()
            pos[b] = pos[a] + vectors[a]
            pos[c] = pos[b] + vectors[b]
            xmin = xmax = ymin = ymax = 0
            xmin = min(xmin, pos[a][0], pos[b][0], pos[c][0])
            xmax = max(xmax, pos[a][0], pos[b][0], pos[c][0])
            ymin = min(ymin, pos[a][1], pos[b][1], pos[c][1])
            ymax = max(ymax, pos[a][1], pos[b][1], pos[c][1])
#            print('pos[%s] = %s  pos[%s] = %s  pos[%s] = %s' % (
#                edge_label(a), pos[a], edge_label(b), pos[b],
#                edge_label(c), pos[c]))

            # spanning tree
            edges = {t:[] for t in range(nf)}
            wait = [start]
            face_seen[start] = True
            q = [start]
            while wait:
                shuffle(wait)
                t = wait.pop()
                t_edges = list(faces[t])
                shuffle(t_edges)
                for e in t_edges:
                    a = ep[e]
                    assert pos[e] is not None
                    assert half_edge_to_face[e] == t
                    f = half_edge_to_face[a]
                    if face_seen[f] is False:
                        edges[t].append(e)
                        face_seen[f] = True
                        q.append(f)
                        wait.append(f)

                        b = fp[a]
                        c = fp[b]
#                        print('add edge (%s,%s,%s) -- %s --> (%s,%s,%s)' % (
#                             edge_label(t_edges[0]),
#                             edge_label(t_edges[1]),
#                             edge_label(t_edges[2]),
#                             edge_label(e),
#                             edge_label(a), edge_label(b), edge_label(c)))
                        if vectors[e] == vectors[ep[e]]:
                            vectors[a] *= -1
                            vectors[b] *= -1
                            vectors[c] *= -1
                        pos[a] = pos[e] + vectors[e]
                        pos[b] = pos[a] + vectors[a]
                        pos[c] = pos[b] + vectors[b]
                        xmin = min(xmin, pos[a][0], pos[b][0], pos[c][0])
                        xmax = max(xmax, pos[a][0], pos[b][0], pos[c][0])
                        ymin = min(ymin, pos[a][1], pos[b][1], pos[c][1])
                        ymax = max(ymax, pos[a][1], pos[b][1], pos[c][1])
#                        print('pos[%s] = %s  pos[%s] = %s  pos[%s] = %s' % (
#                            edge_label(a), pos[a], edge_label(b), pos[b],
#                            edge_label(c), pos[c]))


            # translate
            t = self._V((-xmin, y-ymin))
            for f in q:
#                print('translate %s by %s' % (f, t))
                a,b,c = faces[f]
                pos[a] += t
                pos[b] += t
                pos[c] += t

            # set new height
            y += ymax - ymin + y_space

        n = self._triangulation.num_half_edges()
        for e in range(n):
            if self._pos[e] is None:
                raise RuntimeError('pos[%s] not set properly' % e)

    def _edge_is_boundary(self, e):
        fp = self._triangulation.face_permutation(copy=False)
        ep = self._triangulation.edge_permutation(copy=False)
        pos = self._pos
        vectors = self._vectors
        E = ep[e]
        return pos[fp[e]] != pos[E] or vectors[e] != -vectors[E]

    def glue_side_by_side(self, a):
        r"""
        Move the face to which a belongs so that e is in the middle
        of a quadrilateral.
        """
        if not self._edge_is_boundary(a):
            return

        pos = self._pos
        vectors = self._vectors
        fp = self._triangulation.face_permutation(copy=False)
        ep = self._triangulation.edge_permutation(copy=False)
        A = ep[a]
        b = fp[a]
        c = fp[b]
        if a == A:
            return

        if vectors[a] == vectors[A]:
            vectors[a] *= -1
            vectors[b] *= -1
            vectors[c] *= -1
        pos[a] = pos[A] + vectors[A]
        pos[b] = pos[a] + vectors[a]
        pos[c] = pos[b] + vectors[b]

        self._check()

    def flip(self, e):
        if not self._triangulation.is_forward_flippable(e):
            raise ValueError

        # be sure that e is in the middle of a quadrilateral
        ep = self._triangulation.edge_permutation(copy=False)
        fp = self._triangulation.face_permutation(copy=False)
        E = ep[e]
        pos = self._pos

        if pos is not None:
            self.glue_side_by_side(E)

        # now update
        a = fp[e]; b = fp[a]
        c = fp[E]; d = fp[c]
        vectors = self._vectors
        # x<----------x
        # |     a    ^^
        # |         / |
        # |        /  |
        # |       /   |
        # |b    e/   d|
        # |     /     |
        # |    /      |
        # |   /       |
        # |  /        |
        # | /         |
        # v/    c     |
        # x---------->x

        if pos is not None:
            pos[e] = pos[d]
            pos[E] = pos[b]
        vectors[e] = vectors[d] + vectors[a]
        vectors[E] = vectors[b] + vectors[c]

        self._triangulation.flip(e, vec_slope(vectors[e]))

        self._check()


    ###################################################################
    # Plotting functions
    ###################################################################

    def _plot_edge(self, e, **opts):
        r"""
        Plot the edge ``e``.
        """
        assert self._pos is not None

        pos = self._pos
        vectors = self._vectors
        fp = self._triangulation._fp
        ep = self._triangulation._ep

        oopts = {}
        E = ep[e]
        u = pos[e]
        v = pos[fp[e]]
        if not self._edge_is_boundary(e):
            # the edge is between adjacent faces
            oopts['alpha'] = 0.5
            oopts['linestyle'] = 'dotted'

        oopts['color'] = EDGE_COLORS[self._edge_slope(e)]

        oopts.update(opts)

        L = line2d([u, v], **oopts)

        if e == E:
            # folded edge
            L += point2d([(u + v) / 2], color='black', marker='x', pointsize=100)

        return L

    def _plot_edge_label(self, a, tilde=None, **opts):
        assert self._pos is not None

        fp = self._triangulation.face_permutation(copy=False)
        ep = self._triangulation.edge_permutation(copy=False)
        pos = self._pos
        vectors = self._vectors

        b = fp[a]
        c = fp[b]

        posa = pos[a].n()
        posb = pos[b].n()
        vc = vectors[c].n()
        vc /= vc.norm()
        relposc = posa - vc

        if a == ep[a]:
            # folded edge
            pos = (6.5 * posa + 6.5 * posb + relposc) / 14
        else:
            pos = (8 * posa + 5 * posb + relposc) / 14



        if tilde is None:
            tilde = self._edge_is_boundary(a)

        if tilde:
            if a > ep[a]:
                lab = "%s=~%s"%(a, ep[a])
            else:
                lab = str(a)
        else:
            lab = str(a)

        x, y = self._vectors[a]
        if y.is_zero():
            angle=0
        elif x.is_zero():
            if y > 0:
                angle = 90
            else:
                angle = 270
        else:
            x = float(x)
            y = float(y)
            angle = math.acos(x / math.sqrt(x**2 + y**2))
            if y < 0:
                angle *= -1.0
            angle *= 180 / math.pi

        return text(lab, pos, rotation=angle, color='black')

    def _plot_face(self, a, edge_labels=True):
        r"""
        Plot the face that contains the edge ``a``.
        """
        assert self._pos is not None

        G = Graphics()
        fp = self._triangulation.face_permutation(copy=False)
        b = fp[a]
        c = fp[b]
        pos = self._pos

        # computing slopes in order to determine filling color
        nred = nblue = 0
        for e in (a,b,c):
            slope = self._edge_slope(e)
            if slope == RED:
                nred += 1
            elif slope == BLUE:
                nblue += 1

        if nred == 2:
            color = (.75, 0.5, 0.5)
        elif nblue == 2:
            color = (.5, 0.5, .75)
        else:
            color = (.5, 0.5, 0.5)

        G += polygon2d([pos[a], pos[b], pos[c], pos[a]], alpha=0.41, color=color)

        if edge_labels:
            G += self._plot_edge_label(a)
            G += self._plot_edge_label(b)
            G += self._plot_edge_label(c)

        return G

    def _plot_train_track(self, slope):
        pos = self._pos
        vectors = self._vectors

        V2 = VectorSpace(RDF, 2)
        G = Graphics()

        if slope == HORIZONTAL:
            POS = RED
            NEG = BLUE
            color = 'purple'
        else:
            POS = BLUE
            NEG = RED
            color = 'green'

        for e0, e1, e2 in self._triangulation.faces():
            # determine the large edge
            v0 = vectors[e0]
            v1 = vectors[e1]
            v2 = vectors[e2]
            col0 = RED if v0[0] * v0[1] > 0 else BLUE
            col1 = RED if v1[0] * v1[1] > 0 else BLUE
            col2 = RED if v2[0] * v2[1] > 0 else BLUE
            if col0 == POS and col1 == NEG:
                # e2 is large
                l,s1,s2 = e2,e0,e1
            elif col1 == POS and col2 == NEG:
                # i is large
                l,s1,s2 = e0,e1,e2
            elif col2 == POS and col0 == NEG:
                # j is large
                l,s1,s2 = e1,e2,e0

            pl = V2(pos[l])
            ps1 = V2(pos[s1])
            ps2 = V2(pos[s2])

            cl = (pl + ps1) / 2
            vl = (ps1 - pl)
            cs1 = (ps1 + ps2) / 2
            vs1 = ps2 - ps1
            cs2 = (ps2 + pl) / 2
            vs2 = pl - ps2

            ol = V2((-vl[1], vl[0]))
            ol /= ol.norm()
            os1 = V2((-vs1[1], vs1[0]))
            os1 /= os1.norm()
            os2 = V2((-vs2[1], vs2[0]))
            os2 /= os2.norm()

            G += bezier_path([[cl, cl + 0.3 * ol,
                               cs1 + 0.3 * os1, cs1]], rgbcolor=color)
            G += bezier_path([[cl, cl + 0.3 * ol,
                               cs2 + 0.3 * os2, cs2]], rgbcolor=color)
        return G

    def plot(self, horizontal_train_track=False, vertical_train_track=False, edge_labels=True):
        r"""
        Return a graphics.

        INPUT:

        - ``horizontal_train_track`` - boolean - whether to plot the horizontal
          train-track on the surface

        - ``vertical_train_track`` - boolean - whether to plot the vertical
          train-track on the surface

        EXAMPLES::

            sage: from veerer import *
            sage: faces = "(0, ~3, 4)(1, 2, ~7)(3, ~1, ~2)(5, ~8, ~4)(6, ~5, 8)(7, ~6, ~0)"
            sage: colours = 'RBRRBRBRB'
            sage: T = VeeringTriangulation(faces, colours)
            sage: FS = T.flat_structure_min()
            sage: FS.plot(horizontal_train_track=True)
            sage: FS.plot(vertical_train_track=True)
        """
        if self._pos is None:
            self.set_pos()

        G = Graphics()
        n = self._triangulation.num_half_edges()
        fp = self._triangulation.face_permutation(copy=False)
        ep = self._triangulation.edge_permutation(copy=False)

        # 1. plot faces
        for e in range(n):
            if e < fp[e] and e < fp[fp[e]]:
                G += self._plot_face(e, edge_labels=edge_labels)

        # 2. plot edges
        for e in range(n):
            if self._edge_is_boundary(e) or e <= ep[e]:
                G += self._plot_edge(e)

        # 3. possibly plot train tracks
        if horizontal_train_track:
            G += self._plot_train_track(HORIZONTAL)
        if vertical_train_track:
            G += self._plot_train_track(VERTICAL)

        G.set_aspect_ratio(1)
        G.axes(False)
        return G
