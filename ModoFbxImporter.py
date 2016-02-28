# python
import lx, modo, lxu
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

    def CreateHierarchyRecursive(self, modoHier):
        num = modoHier.fbxNode_.GetChildCount()
        if num == 0: return

        modoScene = self.modoScene_
        for i in range(num):
            fbxChild = modoHier.fbxNode_.GetChild(i)
            nodeAttr = fbxChild.GetNodeAttribute()
            if nodeAttr is not None:
                print nodeAttr.GetAttributeType()
                e = nodeAttr.GetAttributeType()
                # mesh type.
                if e == FbxNodeAttribute.eMesh:
                    thisHier = ModoHierarchy()
                    thisHier.name_ = fbxChild.GetName()
                    thisHier.fbxNode_ = fbxChild
                    thisHier.nodeType_ = "Mesh"
                    thisHier.modoNode_ = modoScene.addMesh(thisHier.name_)
                    self.ReadTransform(thisHier.modoNode_, fbxChild)
                    modoHier.AppendChild(thisHier)
                    self.CreateHierarchyRecursive(thisHier)
                # skeleton joint type.
                elif e == FbxNodeAttribute.eSkeleton:
                    thisHier = ModoHierarchy()
                    thisHier.name_ = fbxChild.GetName()
                    thisHier.fbxNode_ = fbxChild
                    thisHier.nodeType_ = "Skeleton"
                    thisHier.modoNode_ = modoScene.addJointLocator(thisHier.name_)
                    thisHier.ScaleLocatorRadius(0.1)
                    self.ReadTransform(thisHier.modoNode_, fbxChild)
                    modoHier.AppendChild(thisHier)
                    self.CreateHierarchyRecursive(thisHier)
            # group type.
            else:
                thisHier = ModoHierarchy()
                thisHier.name_ = fbxChild.GetName()
                thisHier.fbxNode_ = fbxChild
                thisHier.nodeType_ = "Group"
                thisHier.modoNode_ = modoScene.addJointLocator(thisHier.name_)
                thisHier.ScaleLocatorRadius(0.1)
                self.ReadTransform(thisHier.modoNode_, fbxChild)
                modoHier.AppendChild(thisHier)
                self.CreateHierarchyRecursive(thisHier)

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
        count = fbxMesh.GetControlPointsCount()
        vertices = fbxMesh.GetControlPoints()
        normalMap = None
        globalScale = self.globalScale_
        for i in range(count):
            vertex = vertices[i]
            modoVtx = mesh.geometry.vertices.new((vertex[0] * globalScale, vertex[1] * globalScale, vertex[2] * globalScale))

            # 法線が存在する場合は読み込む
            for j in range(fbxMesh.GetLayerCount()):
                layerNormal = fbxMesh.GetLayer(j).GetNormals()
                if layerNormal:
                    if layerNormal.GetMappingMode() == FbxLayerElement.eByControlPoint:
                        if layerNormal.GetReferenceMode() == FbxLayerElement.eDirect:
                            if normalMap is None:
                                normalMap = mesh.geometry.vmaps.addVertexNormalMap("FBX Normal")
                            normal = layerNormal.GetDirectArray().GetAt(i)
                            normalMap.setNormal((normal[0], normal[1], normal[2]), modoVtx)

    def ReadPolygon(self, mesh, fbxMesh):
        count = fbxMesh.GetPolygonCount()
        vertices = fbxMesh.GetControlPoints() 

        vertexId = 0
        for polyNo in range(count):
            polySize = fbxMesh.GetPolygonSize(polyNo)
            poly = []
            # Make polygon
            for vtxIdx in range(polySize):
                controlPointIdx = fbxMesh.GetPolygonVertex(polyNo, vtxIdx)
                poly.append(controlPointIdx)
            modoPolygon = mesh.geometry.polygons.new(poly)

    def CreateModoMesh(self, modoHier):
        mesh = modoHier.modoNode_
        fbxMesh = modoHier.fbxNode_.GetNodeAttribute()
        # read all vertices.
        self.ReadVertex(mesh, fbxMesh)
        # read all polygons.
        self.ReadPolygon(mesh, fbxMesh)
        # read deformer.
        self.ReadDeformer(mesh, fbxMesh)

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
