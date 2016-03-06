# python
import lx, modo, lxu, sys
from fbx import *

class ModoHierarchy:
    def __init__(self):
        self.name_ = ""
        self.fbxNode_ = None
        self.nodeType_ = "Locator"
        self.modoNode_ = None
        self.children_ = []

    def AppendChild(self, child):
        child.modoNode_.setParent(self.modoNode_, self.modoNode_.childCount())
        self.children_.append(child)

    def FindSkeletonHier(self, name):
        if (self.nodeType_ == "Skeleton") and (self.name_ == name):
            return self
        for child in self.children_:
            ret = child.FindSkeletonHier(name)
            if ret is not None:
                return ret
        return None

    def ListAllMeshesRecursive(self, ret):
        if self.nodeType_ == "Mesh":
            ret.append(self)
        for child in self.children_:
            child.ListAllMeshesRecursive(ret)

    def ListAllMeshes(self):
        ret = []
        self.ListAllMeshesRecursive(ret)
        return ret

    def ScaleLocatorRadius(self, scale):
        if self.modoNode_ is not None:
            rad = self.modoNode_.channel("isRadius")
            if rad is not None:
                rad.set(rad.get() * scale)

class ModoFbxImporter:
    def __init__(self):
        self.path_ = ""
        self.fbxScene_ = None
        self.fbxManager_ = None
        self.modoScene_ = None
        self.hierarchy_ = None
        self.globalScale_ = 1.0

        self.monitor_ = lx.Monitor()

    def GetProgressBar(self, count):
        self.monitor_.init(count)
        return self.monitor_

    def LoadFbxScene(self, path):
        self.path_ = path;
        self.fbxManager_ = FbxManager.Create()
        myIOS = FbxIOSettings.Create(self.fbxManager_, IOSROOT)
        self.fbxManager_.SetIOSettings(myIOS)
        myImporter = FbxImporter.Create(self.fbxManager_, "")
        if not myImporter.Initialize(path, -1, self.fbxManager_.GetIOSettings()) :
            print "Failed to load file (%s)" % (path)
            return False

        self.fbxScene_ = FbxScene.Create(self.fbxManager_, "MyScene")
        myImporter.Import(self.fbxScene_)
        myImporter.Destroy()
        return True

    def EndImport(self):
        if self.fbxManager_ is not None:
            self.fbxManager_.Destroy()

    def ReadTransform(self, node, fbxNode):
        # Translation
        translation = fbxNode.EvaluateLocalTranslation()
        # Rotation
        rotation = fbxNode.EvaluateLocalRotation()
        # Scaling
        scale = fbxNode.EvaluateLocalScaling()
        # set
        globalScale = self.globalScale_
        node.position.set((translation[0] * globalScale, translation[1] * globalScale, translation[2] * globalScale))
        node.rotation.set((lxu.vector.math.radians(rotation[0]), lxu.vector.math.radians(rotation[1]), lxu.vector.math.radians(rotation[2])))
        node.scale.set((scale[0], scale[1], scale[2]))
        # Rotation order
        order = fbxNode.GetRotationOrder(FbxNode.eSourcePivot)
        if order == eEulerXYZ:
            node.rotation.channel("order").set(0)
        elif order == eEulerXZY:
            node.rotation.channel("order").set(1)
        elif order == eEulerYZX:
            node.rotation.channel("order").set(2)
        elif order == eEulerYXZ:
            node.rotation.channel("order").set(3)
        elif order == eEulerZXY:
            node.rotation.channel("order").set(4)
        elif order == eEulerZYX:
            node.rotation.channel("order").set(5)

    def CreateHierarchyChild(self, modoHier, fbxChild, modoNode, nodeType):
        thisHier = ModoHierarchy()
        thisHier.name_ = fbxChild.GetName()
        thisHier.fbxNode_ = fbxChild
        thisHier.nodeType_ = nodeType
        thisHier.modoNode_ = modoNode
        if nodeType != "Mesh":
            thisHier.ScaleLocatorRadius(0.1)
        self.ReadTransform(thisHier.modoNode_, fbxChild)
        modoHier.AppendChild(thisHier)
        self.CreateHierarchyRecursive(thisHier)

    def CreateHierarchyRecursive(self, modoHier):
        num = modoHier.fbxNode_.GetChildCount()
        if num == 0: return

        modoScene = self.modoScene_
        for i in range(num):
            fbxChild = modoHier.fbxNode_.GetChild(i)
            nodeAttr = fbxChild.GetNodeAttribute()
            if nodeAttr is not None:
                e = nodeAttr.GetAttributeType()
                # mesh type.
                if e == FbxNodeAttribute.eMesh:
                    modoNode = modoScene.addMesh(fbxChild.GetName())
                    self.CreateHierarchyChild(modoHier, fbxChild, modoNode, "Mesh")
                # skeleton joint type.
                elif e == FbxNodeAttribute.eSkeleton:
                    modoNode = modoScene.addJointLocator(fbxChild.GetName())
                    self.CreateHierarchyChild(modoHier, fbxChild, modoNode, "Skeleton")
                # others.
                else:
                    modoNode = modoScene.addJointLocator(fbxChild.GetName())
                    self.CreateHierarchyChild(modoHier, fbxChild, modoNode, "Group")
            # group type.
            else:
                modoNode = modoScene.addJointLocator(fbxChild.GetName())
                self.CreateHierarchyChild(modoHier, fbxChild, modoNode, "Group")

    def CreateHierarchy(self):
        if self.fbxScene_ is None:
            return False

        sysUnit = self.fbxScene_.GetGlobalSettings().GetSystemUnit()
        self.globalScale_ = sysUnit.GetConversionFactorTo(FbxSystemUnit.m)

        scene = modo.scene.current()
        self.modoScene_ = scene

        # ルートを作成する
        fbxRoot = self.fbxScene_.GetRootNode()
        self.hierarchy_ = ModoHierarchy()
        self.hierarchy_.name_ = fbxRoot.GetName()
        self.hierarchy_.fbxNode_ = fbxRoot
        self.hierarchy_.modoNode_ = scene.addItem(modo.constants.GROUPLOCATOR_TYPE, self.hierarchy_.name_)
        self.ReadTransform(self.hierarchy_.modoNode_, fbxRoot)
        rootHier = self.hierarchy_

        # Z-upの場合、これを補正するロケータを作成する
        axisSys = self.fbxScene_.GetGlobalSettings().GetAxisSystem()
        axisInfo = axisSys.GetUpVector()
        if axisInfo[0] == FbxAxisSystem.eZAxis:
            sceneUp = ModoHierarchy()
            sceneUp.name_ = "YUpConversionLocator"
            sceneUp.fbxNode_ = fbxRoot
            sceneUp.modoNode_ = scene.addJointLocator(sceneUp.name_)
            sceneUp.modoNode_.rotation.set((lxu.vector.math.radians(-90 * axisInfo[1]), 0, 0))
            rootHier.AppendChild(sceneUp)
            rootHier = sceneUp

        # ルートノード直下にノードが1つしかなく、且つこれがNullノードの場合は無視する
        if fbxRoot.GetChildCount() == 1:
            fbxChild = fbxRoot.GetChild(0)
            nodeAttr = fbxChild.GetNodeAttribute()
            if (nodeAttr is not None) and (nodeAttr.GetAttributeType() == FbxNodeAttribute.eNull):
                rootHier.fbxNode_ = fbxChild

        self.CreateHierarchyRecursive(rootHier)

    def ReadDeformer(self, mesh, fbxMesh):
        skinCount = fbxMesh.GetDeformerCount(FbxDeformer.eSkin)
        if skinCount == 0: return

        scene = self.modoScene_
        rootHier = self.hierarchy_

        # normalizeグループを作成し、deformersへ接続する
        deformers = mesh.itemGraph("deformers")
        normalizeFolder = scene.addItem(modo.constants.DEFORMGROUP_TYPE)
        normalizeFolder >> deformers

        numVertices = mesh.geometry.numVertices
        for i in range(skinCount):
            clusterCount = fbxMesh.GetDeformer(i, FbxDeformer.eSkin).GetClusterCount()
            # Clusterの数だけWeightmapを作成する
            for j in range(clusterCount):
                # FBX cluster info.
                cluster = fbxMesh.GetDeformer(i, FbxDeformer.eSkin).GetCluster(j)
                link = cluster.GetLink()
                indexCount = cluster.GetControlPointIndicesCount()
                indices = cluster.GetControlPointIndices()
                weights = cluster.GetControlPointWeights()
                if (link is not None) and (indexCount > 0):
                    # Weightmapを作成し、ウェイト値を設定
                    weightMap = mesh.geometry.vmaps.addWeightMap(link.GetName(), 0.0)
                    for k in range(indexCount):
                        weightMap[indices[k]] = weights[k]
                    mesh.geometry.setMeshEdits()
                    # Weightmapと対応するJointをdeformersに接続する
                    lx.eval("anim.setup on") # セットアップモードをONにしないとうまくいかない場合がある
                    targetHier = rootHier.FindSkeletonHier(link.GetName())
                    influ = scene.addItem(modo.constants.GENINFLUENCE_TYPE)
                    targetHier.modoNode_ >> influ
                    influ >> normalizeFolder
                    influ >> deformers
                    influ.channel("type").set("mapWeight")
                    influ.channel("name").set(weightMap.name)
                    lx.eval("anim.setup off") # セットアップモード終了

    def ReadVertex(self, mesh, fbxMesh):
        # 法線レイヤーが存在するなら事前に取得しておく
        normalMap = None
        fbxNormal = None
        count = fbxMesh.GetLayerCount()
        for j in range(count):
            layerNormal = fbxMesh.GetLayer(j).GetNormals()
            if layerNormal:
                if layerNormal.GetMappingMode() == FbxLayerElement.eByControlPoint:
                    if layerNormal.GetReferenceMode() == FbxLayerElement.eDirect:
                        normalMap = mesh.geometry.vmaps.addVertexNormalMap("FBX Normal")
                        fbxNormal = layerNormal

        # 頂点情報を読み込む
        count = fbxMesh.GetControlPointsCount()
        vertices = fbxMesh.GetControlPoints()
        modoVertices = mesh.geometry.vertices
        globalScale = self.globalScale_
        mon = self.GetProgressBar(count)
        for (i, vertex) in enumerate(vertices):
            if mon.step(1): sys.exit("LXe_ABORT")
            modoVertices._accessor.New((vertex[0] * globalScale, vertex[1] * globalScale, vertex[2] * globalScale))
        if normalMap is not None:
            for (i, modoVtx) in enumerate(modoVertices):
                normal = fbxNormal.GetDirectArray().GetAt(i)
                normalMap.setNormal((normal[0], normal[1], normal[2]), modoVtx)

    def ReadPolygon(self, mesh, fbxMesh):
        count = fbxMesh.GetPolygonCount()
        vertices = fbxMesh.GetControlPoints() 

        mon = self.GetProgressBar(count)
        for polyNo in range(count):
            if mon.step(1): sys.exit("LXe_ABORT")
            polySize = fbxMesh.GetPolygonSize(polyNo)
            poly = []
            # Make polygon
            for vtxIdx in range(polySize):
                controlPointIdx = fbxMesh.GetPolygonVertex(polyNo, vtxIdx)
                poly.append(controlPointIdx)
            modoPolygon = mesh.geometry.polygons.new(poly)

    def ReadUV(self, mesh, fbxMesh):
        count = fbxMesh.GetElementUVCount()
        for uvMapIdx in range(count):
            # Get fbx uv map and Create modo uv map.
            fbxMap = fbxMesh.GetElementUV(uvMapIdx)
            modoMap = mesh.geometry.vmaps.addUVMap(fbxMap.GetName())

            # Get fbx uv.
            mapMode = fbxMap.GetMappingMode()
            refMode = fbxMap.GetReferenceMode()
            if mapMode == FbxLayerElement.eByControlPoint:
                if refMode == FbxLayerElement.eDirect:
                    # Vertex direct mode.
                    darr = fbxMap.GetDirectArray()
                    vcount = darr.GetCount()
                    mon = self.GetProgressBar(vcount)
                    for vIdx in range(vcount):
                        if mon.step(1): sys.exit("LXe_ABORT")
                        uv = darr.GetAt(vIdx)
                        modoMap[vIdx] = (uv[0], uv[1])
                elif refMode == FbxLayerElement.eIndexToDirect:
                    # Vertex index mode.
                    iarr = fbxMap.GetIndexArray()
                    darr = fbxMap.GetDirectArray()
                    vcount = iarr.GetCount()
                    mon = self.GetProgressBar(vcount)
                    for vIdx in range(vcount):
                        if mon.step(1): sys.exit("LXe_ABORT")
                        uv = darr.GetAt(iarr.GetAt(vIdx))
                        modoMap[vIdx] = (uv[0], uv[1])
            elif mapMode == FbxLayerElement.eByPolygonVertex:
                # Polygon mode.
                darr = fbxMap.GetDirectArray()
                mon = self.GetProgressBar(len(mesh.geometry.polygons))
                for (pIdx, poly) in enumerate(mesh.geometry.polygons):
                    if mon.step(1): sys.exit("LXe_ABORT")
                    for vIdx in xrange(poly.numVertices):
                        idx = fbxMesh.GetTextureUVIndex(pIdx, vIdx)
                        uv = darr.GetAt(idx)
                        poly.setUV((uv[0], uv[1]), vIdx, modoMap)

    def ReadMaterial(self, mesh, fbxMesh):
        scene = modo.scene.current()
        # Add material.
        fbxNode = fbxMesh.GetNode()
        count = fbxNode.GetMaterialCount()
        modoMats = []
        for i in xrange(count):
            fbxMat = fbxNode.GetMaterial(i)
            diff = fbxMat.Diffuse.Get()
            modoMat = scene.addMaterial(name=fbxMat.GetName())
            modoMat.channel('diffCol').set((diff[0], diff[1], diff[2]))
            modoMats.append(modoMat)

        # Check material all same.
        count = fbxMesh.GetElementMaterialCount()
        allSameMatId = -1
        for i in xrange(count):
            matElem = fbxMesh.GetElementMaterial(i)
            if matElem.GetMappingMode() == FbxLayerElement.eAllSame:
                allSameMatId = matElem.GetIndexArray().GetAt(0)
                break

        if allSameMatId >= 0:
            # Assign material all same.
            matName = modoMats[allSameMatId].name
            mon = self.GetProgressBar(len(mesh.geometry.polygons))
            for poly in mesh.geometry.polygons:
                if mon.step(1): sys.exit("LXe_ABORT")
                poly.materialTag = matName
        else:
            # Assign material by polygon.
            for i in xrange(count):
                matElem = fbxMesh.GetElementMaterial(i)
                if matElem.GetMappingMode() == FbxLayerElement.eByPolygon:
                    indexArray = matElem.GetIndexArray()
                    mon = self.GetProgressBar(len(mesh.geometry.polygons))
                    for (j, poly) in enumerate(mesh.geometry.polygons):
                        if mon.step(1): sys.exit("LXe_ABORT")
                        poly.materialTag = modoMats[indexArray.GetAt(j)].name
                    break;

    def CreateModoMesh(self, modoHier):
        mesh = modoHier.modoNode_
        fbxMesh = modoHier.fbxNode_.GetNodeAttribute()
        # read all vertices.
        self.ReadVertex(mesh, fbxMesh)
        # read all polygons.
        self.ReadPolygon(mesh, fbxMesh)
        # read all UVs.
        self.ReadUV(mesh, fbxMesh)
        # read deformer.
        self.ReadDeformer(mesh, fbxMesh)
        # read materials.
        self.ReadMaterial(mesh, fbxMesh)

if __name__ == '__main__':
    # ファイルオープンダイアログを表示する
    filepath = modo.dialogs.customFile('fileOpen', 'FBX 2016', ('fbx',), ('FBX 2016 File',), ('*.fbx',))
    if (filepath is not None) and (len(filepath) > 0):
        importer = ModoFbxImporter()

        # FBXを読み込む
        importer.LoadFbxScene(filepath)

        # 階層構造を作成する
        importer.CreateHierarchy()

        # メッシュリストを作成する
        meshList = importer.hierarchy_.ListAllMeshes()

        # メッシュを作成する
        for mesh in meshList:
            importer.CreateModoMesh(mesh)

        # インポート終了
        importer.EndImport()
