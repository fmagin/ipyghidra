
import zipfile

import json
import re
from inspect import Signature, Parameter

import tempfile
import os

import ghidra_bridge




class DocHelper():
    """Doc helper that is based on ghidradoc.py helper, but returns the doc dict instead of printing it"""

    def __init__(self, bridge: ghidra_bridge.bridge.BridgeClient, zip_path=None):

        self._zip_path = zip_path or self._find_zip(bridge)
        self._bridge = bridge
        self._ghidra = bridge.remote_import('ghidra')
        with zipfile.ZipFile(self._zip_path, "r") as fzip:
            self._doc_dir = tempfile.TemporaryDirectory()
            fzip.extractall(self._doc_dir.name)


    def _find_zip(self, bridge: ghidra_bridge.bridge.BridgeClient) -> str:
        # Find the API ZIP so the client can inspect the doc
        ghidra = bridge.remote_import('ghidra')
        layout = ghidra.GhidraApplicationLayout()
        install_dir = layout.applicationInstallationDir.absolutePath
        import os

        if ghidra.util.SystemUtilities.isInDevelopmentMode():
            # For a git checkout `install_dir` will e.g. be `/home/user/gits` if the repo was cloned to `/home/user/gits/ghidra`
            # To prevent hardcoding assumptions like the repo folder being named "ghidra", we will search through the root directories instead
            # Root directory should be `/home/user/gits/ghidra/Ghidra` in this case.
            for root in layout.applicationRootDirs:
                path = os.path.join(os.path.dirname(root.absolutePath), "build", "tmp", "GhidraAPI_javadoc.zip")
                if os.path.exists(path):
                    return path
            else:
                raise FileNotFoundError(f"Could not find doc at {path}. Run `gradle zipJavadocs` to create it.")
        else:
            path = os.path.join(install_dir, "docs", "GhidraAPI_javadoc.zip")
            if os.path.exists(path):
                return path
            raise FileNotFoundError(f"Could not find doc at {path}")



    def get_jsondoc(self, class_name):
        "cls is a string of the classpath e.g. 'ghidra.program.database.ProgramDB'"
        json_path = os.path.join("api", *class_name.split('.')) + '.json'
        with open(os.path.join(self._doc_dir.name, json_path)) as f:
            return json.load(f)



    def _get_class_and_method(self, obj):
        """A collection of hacks and string extraction taken straigt from the original ghidradoc.py"""
        class_name = None
        method_name = None

        t = str(obj._bridged_get_type())

        if "instancemethod" in t:
            # we have a callable. use obj._bridge_repr because the type info is useless
            t = obj._bridge_repr
            tokens = str(t).split(" ")[2].split(".")
            class_name = ".".join(tokens[:-1])
            method_name = tokens[-1]
        else:
            match = re.search("'(.*)'", t)
            if match is not None:
                class_name = match.group(1)

        return class_name, method_name


    def get_doc(self, obj):
        class_name, method_name = self._get_class_and_method(obj)


        try_again = True
        while try_again:
            try_again = False
            jdoc = self.get_jsondoc(class_name)
            if method_name is None:
                return jdoc
            else:
                method_doc = next((x for x in jdoc['methods'] if x['name'] == method_name), None)
                if method_doc:
                    return method_doc
                else:
                    if 'extends' in jdoc:
                        class_name = jdoc['extends']
                        try_again = True

    def render_method(self, json_doc) -> str:
        jd = json_doc
        return f"""
        {jd['name']}({", ".join([f"{p['name']}: {p['type_short']}" for p in jd['params']])}) -> {jd['return']['type_short']}
        {jd['javadoc']}
        """

    def get_annotations(self, function):
        json_doc = self.get_doc(function)
        a = { param['name']: param['type_long'] for param in json_doc['params']}
        a['return'] = json_doc['return']['type_long']
        return a

    def get_signature(self, function) -> Signature:
        json_doc = self.get_doc(function)
        parameters = [ Parameter(param['name'], annotation=param['type_short'], kind=Parameter.POSITIONAL_OR_KEYWORD) for param in json_doc['params']]
        return Signature(parameters, return_annotation=json_doc['return']['type_short'], __validate_parameters__ = False)


    def patch_ghidra_bridge(self):
        from ghidra_bridge.bridge import BridgedCallable, BridgedObject

        def __signature__(target_self):
            return self.get_signature(target_self)

        def __annotations__(target_self):
            return self.get_annotations(target_self)

        def __doc__(target_self):
            try:
                return self.get_doc(target_self)['javadoc']
            except:
                pass

        setattr(BridgedObject, '__doc__', property(__doc__))
        getattr(BridgedObject, '_LOCAL_METHODS').extend(['__doc__', '__annotations__', '__signature__'])
        setattr(BridgedCallable, '__doc__', property(__doc__))
        setattr(BridgedCallable, '__annotations__', property(__annotations__))
        setattr(BridgedCallable, '__signature__', property(__signature__))









