
import zipfile

import json
import re
from inspect import Signature, Parameter

import tempfile
import os

import ghidra_bridge



from typing import NewType, Tuple, Optional, TypeVar, List, TYPE_CHECKING



T = TypeVar('T')
def unwrap(input: Optional[T]) -> T:
    if input is None:
        raise Exception("Unwrap called on None")
    else:
        return input
ClassName = NewType("ClassName", str)
MethodName = NewType("MethodName", str)



if TYPE_CHECKING:
    from typing import TypedDict
    class ParameterDoc(TypedDict):
        type_long: ClassName
        name: str
        comment: str
        type_short: str

    class MethodDoc(TypedDict):
        javadoc: str
        static: bool
        name: str
        comment: str
        params: List[ParameterDoc]
        throws: List[ClassName]
        _return: str

from inspect import _signature_from_callable

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



    def _get_class_and_method(self, obj) -> Tuple[ClassName, Optional[MethodName], bool]:
        """A collection of hacks and string extraction mostly taken from the original ghidradoc.py"""
        class_name: Optional[ClassName] = None
        method_name: Optional[MethodName] = None
        is_class = False
        t = str(obj._bridged_get_type())

        if "<type 'java.lang.Class'>" == t:
            # this is a Class that isn't instantiated yet
            # Get the string representation which should look like "<type 'ghidra.app.util.cparser.C.CParserUtils'>" again
            is_class = True
            t = str(obj)

        if "instancemethod" in t:
            # we have a callable. use obj._bridge_repr because the type info is useless
            t = obj._bridge_repr
            tokens = str(t).split(" ")[2].split(".")
            class_name = ClassName(".".join(tokens[:-1]))
            method_name = MethodName(tokens[-1])
        else:
            match = re.search("'(.*)'", t)
            if match is not None:
                class_name = ClassName(match.group(1))

        return unwrap(class_name), method_name, is_class


    def _generate_constructor_doc(self, jdoc):
        """

        :param jdoc: The json doc of the class
        :type jdoc:
        :return:
        :rtype:
        """
        # Do we have multiple constructors?

        # A type/class was passed in. The most useful result to return is the doc of the constructor, but there might be multiple
        # TODO: If a class doesn't implement it's own constructor we might still have to search for an implementation
        constructors = [c for c in jdoc['methods'] if c['name'] == "<init>"]
        if len(constructors) > 1:
            # TODO: Find a sensible solution here.
            # For now this does also just returns the first constructor
            constructors[0]['javadoc'] = f"[Constructor for {class_name}: {jdoc['javadoc']}]\n" + constructor_doc[0][
                'javadoc']
            return constructor_doc[0]
        else:
            constructor_doc[0]['javadoc'] = f"[Constructor for {class_name}: {jdoc['javadoc']}]\n" + constructor_doc[0][
                'javadoc']
            return constructor_doc[0]


    def get_doc(self, obj):
        class_name, method_name, is_class = self._get_class_and_method(obj)

        if is_class:
            pass

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

    def _get_doc(self, class_name: ClassName):
        pass

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

        setattr(BridgedObject, 'getdoc', __doc__)
        setattr(BridgedCallable, 'getdoc', property(__doc__))
        setattr(BridgedCallable, '__annotations__', property(__annotations__))
        setattr(BridgedCallable, '__signature__', property(__signature__))









