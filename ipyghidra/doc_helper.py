import functools
import zipfile
import logging
import json
import re
from inspect import Signature, Parameter

import tempfile
import os


from IPython.core.oinspect import _render_signature
from ghidra_bridge.bridge import BridgeClient

import attr
import cattr

from typing import NewType, Tuple, Optional, TypeVar, List, Any, Dict

T = TypeVar('T')


def unwrap(opt: Optional[T]) -> T:
    if opt is None:
        raise Exception("Unwrap called on None")
    else:
        return opt


ClassName = NewType("ClassName", str)
MethodName = NewType("MethodName", str)

cattr.register_structure_hook(ClassName, lambda x, cls: x)
cattr.register_structure_hook(MethodName, lambda x, cls: x)


logger = logging.getLogger(__name__)


@attr.s
class ParameterDoc:
    type_long: ClassName = attr.ib()
    name: str = attr.ib()
    comment: str = attr.ib()
    type_short: str = attr.ib()


@attr.s
class ReturnDoc:
    type_long: ClassName = attr.ib()
    comment: str = attr.ib()
    type_short: str = attr.ib()


@attr.s
class MethodDoc:
    javadoc: str = attr.ib()
    static: bool = attr.ib()
    name: str = attr.ib()
    comment: str = attr.ib()
    params: List[ParameterDoc] = attr.ib()
    throws: List[ClassName] = attr.ib()
    returns: ReturnDoc = attr.ib()

    def to_annotation(self) -> Dict[str, Any]:
        a = {param.name: param.type_long for param in self.params}
        a['return'] = self.returns.type_long
        return a

    def to_signature(self) -> Signature:
        parameters = [Parameter(param.name, annotation=param.type_short, kind=Parameter.POSITIONAL_OR_KEYWORD) for param
                      in self.params]
        return Signature(parameters, return_annotation=self.returns.type_short, __validate_parameters__=False)


@attr.s
class FieldDoc:
    type_long: ClassName = attr.ib()
    javadoc: str = attr.ib()
    static: bool = attr.ib()
    name: str = attr.ib()
    comment: str = attr.ib()
    type_short: str = attr.ib()
    constant_value: Optional[Any] = attr.ib()


@attr.s
class ClassDoc:
    implements: List[ClassName] = attr.ib()
    javadoc: str = attr.ib()
    static: bool = attr.ib()
    extends: ClassName = attr.ib()
    methods: List[MethodDoc] = attr.ib()
    name: str = attr.ib()
    comment: str = attr.ib()
    fields: List[FieldDoc] = attr.ib()


class DocHelper:
    """Doc helper that is based on ghidradoc.py helper, but returns the doc dict instead of printing it"""

    def __init__(self, bridge: BridgeClient, zip_path=None):

        self._zip_path = zip_path or self._find_zip(bridge)
        self._bridge = bridge
        self._ghidra = bridge.remote_import('ghidra')
        with zipfile.ZipFile(self._zip_path, "r") as fzip:
            self._doc_dir = tempfile.TemporaryDirectory()
            fzip.extractall(self._doc_dir.name)

    def __repr__(self):
        return f"<DocHelper at {self._doc_dir.name}>"

    @staticmethod
    def _find_zip(bridge: BridgeClient) -> str:
        # Find the API ZIP so the client can inspect the doc
        ghidra = bridge.remote_import('ghidra')
        layout = ghidra.GhidraApplicationLayout()
        install_dir = layout.applicationInstallationDir.absolutePath
        import os

        if ghidra.util.SystemUtilities.isInDevelopmentMode():
            # For a git checkout `install_dir` will e.g. be `/home/user/gits` if the repo was cloned to `/home/user/gits/ghidra`
            # To prevent hardcoding assumptions like the repo folder being named "ghidra", we will search through the root directories instead
            # Root directory should be `/home/user/gits/ghidra/Ghidra` in this case.
            path = None
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

    def _fix_doc(self, doc_dict):
        if isinstance(doc_dict, dict):
            if 'return' in doc_dict:
                doc_dict['returns'] = doc_dict.pop('return')
            return {k: self._fix_doc(v) for k, v in doc_dict.items()}
        elif isinstance(doc_dict, list):
            return [self._fix_doc(i) for i in doc_dict]
        else:
            return doc_dict

    @functools.lru_cache(maxsize=128)
    def get_jsondoc(self, class_name: ClassName) -> Optional[ClassDoc]:
        """cls is a string of the classpath e.g. 'ghidra.program.database.ProgramDB'"""
        json_path = os.path.join("api", *class_name.split('.')) + '.json'
        path = os.path.join(self._doc_dir.name, json_path)
        logger.debug("Trying to open file %s for doc of %s", path, class_name)
        try:
            with open(path) as f:
                logger.debug("Found doc for %s at %s", class_name, path)
                return cattr.structure(self._fix_doc(json.load(f)), ClassDoc)
        except FileNotFoundError:
            logger.info("Failed to find doc for %s", class_name)
            return None

    @staticmethod
    def _get_class_and_method(obj) -> Tuple[ClassName, Optional[MethodName], bool]:
        """A collection of hacks and string extraction mostly taken from the original ghidradoc.py"""
        class_name: Optional[ClassName] = None
        method_name: Optional[MethodName] = None
        is_class = False
        t = str(obj._bridged_get_type())
        b_repr = obj._bridge_repr
        if "<type 'java.lang.Class'>" == t:
            # this is a Class that isn't instantiated yet
            # The string representation should again look like "<type 'ghidra.app.util.cparser.C.CParserUtils'>" again
            is_class = True
            t = str(obj)
        if "<java constructor" in b_repr:
            class_name = ClassName(str(b_repr).split(" ")[2])
            return class_name, MethodName("<init>"), True

        if "instancemethod" in t:
            # we have a callable. use obj._bridge_repr because the type info is useless
            t = obj._bridge_repr
            tokens = str(t).split(" ")[2].split(".")
            # For some reason when IPython requests __init__ of a class the result here can be something like
            # ['ghidra', 'program', 'database', 'ProgramDB', 'ghidra', 'program', 'database', 'ProgramDB']
            if tokens[:len(tokens) // 2] == tokens[len(tokens) // 2:]:
                class_name = ClassName(".".join(tokens[:len(tokens) // 2]))
                method_name = MethodName("<init>")
            else:
                class_name = ClassName(".".join(tokens[:-1]))
                method_name = MethodName(tokens[-1])
        else:
            match = re.search("'(.*)'", t)
            if match is not None:
                class_name = ClassName(match.group(1))
        return class_name, method_name, is_class

    @staticmethod
    def _is_class(obj) -> bool:
        """
        Check if some object is a Bridged Class (so the object of a Java class)
        :param obj:
        :return:
        """
        return "<type 'java.lang.Class'>" == str(obj._bridged_get_type())

    @staticmethod
    def _generate_constructor_doc(class_doc: ClassDoc) -> Tuple[ClassDoc, Optional[MethodDoc]]:
        """

        :param class_doc: The json doc of the class
        :type class_doc:
        :return:
        :rtype:
        """
        # Do we have multiple constructors?

        # A type/class was passed in. The most useful result to return is the doc of the constructor
        # but there might be multiple
        # TODO: If a class doesn't implement it's own constructor we might still have to search for an implementation
        constructors = [c for c in class_doc.methods if c.name == "<init>"]
        if len(constructors) > 1:
            constructor_docs = "\n".join([_render_signature(c.to_signature(), class_doc.name) for c in constructors])
            jdoc = f"""[ Available constructors for '{class_doc.name}: {class_doc.javadoc}']
{constructor_docs}"""
            class_doc = attr.evolve(class_doc, javadoc=jdoc)

            return class_doc, None
        else:
            constructor = constructors[0]
            return class_doc, constructor

    def get_doc(self, obj) -> Tuple[ClassDoc, Optional[MethodDoc]]:
        class_name, method_name, is_class = self._get_class_and_method(obj)
        return self._get_doc(class_name, method_name)

    @functools.lru_cache(maxsize=128)
    def _get_doc(self, class_name: ClassName, method_name: MethodName):
        orig_class_name = class_name

        try_again = True
        while try_again:
            try_again = False
            jdoc = self.get_jsondoc(class_name)
            if method_name is None:
                return jdoc, None
            else:
                method_doc = next((x for x in jdoc.methods if x.name == method_name), None)
                if method_doc:
                    return self.get_jsondoc(orig_class_name), method_doc
                else:
                    class_name = jdoc.extends
                    try_again = True

    def get_annotations(self, function):
        class_doc, method_doc = self.get_doc(function)
        if method_doc:
            return method_doc.to_annotation()

    def get_signature(self, function) -> Signature:
        class_doc, method_doc = self.get_doc(function)
        if self._is_class(function):
            class_doc, method_doc = self._generate_constructor_doc(class_doc)
        if method_doc:
            return method_doc.to_signature()


    def patch_ghidra_bridge(self):
        from ghidra_bridge.bridge import BridgedCallable, BridgedObject

        def __signature__(target_self):
            return self.get_signature(target_self)

        def __annotations__(target_self):
            return self.get_annotations(target_self)

        def __doc__(target_self):
            try:
                class_doc, method_doc = self.get_doc(target_self)
                if method_doc and method_doc.name == '<init>':
                    class_doc, method_doc = self._generate_constructor_doc(class_doc)
                if method_doc:
                    return method_doc.javadoc
                else:
                    return class_doc.javadoc
            except Exception as e:
                logger.warning(f"Got Exception {e} when generating __doc__ for {target_self}")
                pass

        setattr(BridgedObject, 'getdoc', __doc__)
        setattr(BridgedCallable, 'getdoc', __doc__)
        def __subclasses__(target_self):
            return []

        setattr(BridgedObject, '__subclasses__', __subclasses__)
        setattr(BridgedCallable, '__annotations__', property(__annotations__))
        setattr(BridgedCallable, '__signature__', property(__signature__))

        import inspect

        def isclass(object):
            if isinstance(object, BridgedObject):
                return object._bridge_type == 'Class'
            else:
                return isinstance(object, type)

        setattr(inspect, 'isclass', isclass)