import inspect
import logging
from collections import defaultdict
from functools import cached_property, lru_cache
from inspect import Signature
from typing import Optional, List, Dict, Union, Tuple

import jfx_bridge
from jfx_bridge.bridge import BridgedObject, BridgedCallable, ConcedeBridgeOverrideException

from pathlib import Path

from mypy.modulefinder import SearchPaths, FindModuleCache, ModuleNotFoundReason

from distutils.sysconfig import get_python_lib

search_paths = SearchPaths((),(),(get_python_lib(),),())

find_module_cache = FindModuleCache(search_paths)

from typed_ast.ast3 import parse, dump, NodeVisitor, get_docstring, Attribute, Name

from typed_ast._ast3 import FunctionDef, ClassDef


logging.basicConfig(
format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
level=logging.INFO,
datefmt='%Y-%m-%d %H:%M:%S')

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def extract_typestr_from_bridged_class(bridged_class: BridgedCallable):
    return str(bridged_class)[7:-2]


class ClassFinder(NodeVisitor):
    def __init__(self):
        self.classes = []

    def visit_ClassDef(self, node):
        self.classes.append(node)



class FuncDefFinder(NodeVisitor):
    def __init__(self):
        self.functions = []

    def visit_FunctionDef(self, node):
        self.functions.append(node)

class BaseDoc():
    pass

class ClassDoc(BaseDoc):
    # Cache that maps from "ghidra.program.database.ProgramDB" to the ClassDoc object for that class
    _cache = {}


    def __init__(self, cls_obj: Optional[BridgedCallable] = None, cls_string: Optional[str] = None):
        # self.cls = cls
        if cls_string in ClassDoc._cache:
            raise RuntimeError("__init__ of ClassDoc called while already cached")
        else:
            ClassDoc._cache[cls_string] = self
        if cls_obj is not None and cls_obj._bridge_type == 'Class':
            self.cls_type = True
            self.cls_string = cls_obj.__init__.__name__
        elif cls_obj is not None and cls_obj._bridge_type == 'type':
            raise NotImplementedError()

        else:
            self.cls_string = cls_string or cls_obj._bridge_type
            self.cls_type = False

        if self.cls_string in ['__call__']:
            raise ValueError("cls_string is %s, this shouldnt' have happened" % self.cls_string)
        self._ast = None

    @staticmethod
    def from_cls_string(cls_string: str):
        # like ghidra.program.database.ProgramDB
        try:
            return ClassDoc._cache[cls_string]
        except KeyError:
            ClassDoc._cache[cls_string] = ClassDoc(cls_string=cls_string)
            return ClassDoc._cache[cls_string]

    @cached_property
    def functions(self):
        ff = FuncDefFinder()
        ff.visit(self.ast)
        return ff.functions

    @cached_property
    def __doc__(self):
        ast = self.ast
        doc = get_docstring(ast)
        return doc

    @cached_property
    def ast(self) -> ClassDef:
        if not self._ast:
            source = self.source_file.read_text()
            file_ast = parse(source, self.source_file)
            cf = ClassFinder()
            cf.visit(file_ast)
            self._ast = cf.classes[0]
        return self._ast


    @cached_property
    def source_file(self) -> Path:

        result = find_module_cache.find_module(self.cls_string)
        if isinstance(result, str):
            return Path(result)
        elif isinstance(result, ModuleNotFoundReason):
            raise ValueError(result)


def _type_str(bridged_obj: BridgedObject):
    _t = bridged_obj._bridged_get_type()  # "<type 'ghidra.program.database.ProgramDB'>"
    return str(_t)[7:-2]  # 'ghidra.program.database.ProgramDB'


class InstanceMethodDoc(BaseDoc):

    def __init__(self, bridged_callable: BridgedCallable):

        if bridged_callable._bridge_type == "reflectedconstructor":
            # Case for: <java constructor ghidra.GhidraApplicationLayout 0x19b64>
            self.cls_doc = ClassDoc.from_cls_string(cls_string=bridged_callable.__name__)
            self.name = bridged_callable.__name__
        elif bridged_callable._bridge_type == "Class":
            # case for <type 'ghidra.app.util.cparser.C.CompositeHandler'>
            ty_name = bridged_callable.typeName
            self.cls_doc = ClassDoc.from_cls_string(ty_name)
            self.name = ty_name
        else:
            try:
                ty = bridged_callable.im_class
                if ty._bridge_type == "type":
                    # Case for: <bound method reflectedconstructor.__call__ of <java constructor ghidra.GhidraApplicationLayout 0x19b64>>
                    cls_string = bridged_callable.im_self.__name__
                    self.cls_doc = ClassDoc.from_cls_string(cls_string)
                    self.name = cls_string
                elif bridged_callable._bridge_type == "instancemethod":
                    # Case for: <bound method ghidra.program.database.ProgramDB.ghidra.program.database.ProgramDB of dkacstm-lan-3_3_6.elf - .ProgramDB>
                    self.cls_doc = ClassDoc.from_cls_string(bridged_callable.im_self._bridge_type)
                    self.name = bridged_callable.__name__
                # elif ty._bridge_type == "Class":
                #     # Case for: <type 'ghidra.GhidraApplicationLayout'>
                #     cls_string = bridged_callable.typeName
                #     self.cls_doc = ClassDoc(cls_string=cls_string)
                #     self.name = cls_string
                else:
                    self.cls_doc = ClassDoc(cls_obj=ty)
                    self.name = bridged_callable.__name__
            except AttributeError as e:
                # TODO: Remove if sure that this isn't needed
                if bridged_callable._bridge_type == "instancemethod":
                    self.cls_doc = ClassDoc(cls_string=bridged_callable.im_self._bridge_type)
                    self.name = bridged_callable.__name__

                else:
                    self.cls_doc = ClassDoc(None, cls_string=bridged_callable.__name__)
                    self.name = bridged_callable.__name__

        if self.reflectedconstructor:
            x = 1

        self._asts: Optional[FunctionDef] = None

    @lru_cache()
    def get_annotations(self) -> Dict[str, str]:
        if not self.overloaded:
            return dict(self._ast_to_annotations(self.ast))
        else:
            logger.info("get_annotations: %s() has multiple implementations, not handled yet", self.name)

    @lru_cache()
    def get_signature(self) -> inspect.Signature:
        if not self.overloaded:
            parameters = [inspect.Parameter(name,
                                            annotation=ty,
                                            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD
                                            ) for
                          name, ty
                          in self._ast_to_annotations(self.ast) if name != "return"]
            return Signature(parameters, return_annotation=self.get_annotations()["return"], __validate_parameters__=False)
        else:
            logger.info("get_signature: %s() has multiple implementations, not handled yet", self.name)

    @lru_cache()
    def _ast_to_annotations(self, ast: FunctionDef)-> List[Tuple[str, str]]:
        result = []
        for arg in ast.args.args:
            result.append( (arg.arg, self._attr_to_str(arg.annotation)))

        result.append( ( 'return' , self._attr_to_str(ast.returns) ))
        return result

    def _attr_to_str(self, ast: Union[Attribute, Name]) -> str:
        if isinstance(ast, Name):
            return ast.id
        elif isinstance(ast, Attribute):
            return self._attr_to_str(ast.value) + "." + ast.attr


    @cached_property
    def is_constructor(self):
        return self.reflectedconstructor or self.name == self.cls_doc.cls_string

    @cached_property
    def reflectedconstructor(self):
        return self.cls_doc.cls_string == "reflectedconstructor"

    @cached_property
    def possible_asts(self) -> List[FunctionDef]:
        name = "__init__" if self.is_constructor else self.name
        if not self._asts:
            self._asts = list(filter(lambda f: f.name == name, self.cls_doc.functions))

        return self._asts

    @cached_property
    def overloaded(self) -> bool:
        return len(self.possible_asts) > 1

    @cached_property
    def ast(self) -> Optional[FunctionDef]:
        if not self.overloaded:
            return self.possible_asts[0]
        else:
            return None

    @cached_property
    def __doc__(self) -> str:
        if not self.overloaded:
            return get_docstring(self.ast) or "NO JAVADOC AVAILABLE"
        else:
            msg = "%s() has multiple implementations, not handled yet" % self.name
            logger.info(msg)
            return msg

class DocHelper():
    def __init__(self, bridge):
        self.bridge = bridge
    pass
    from jfx_bridge.bridge import BridgedCallable, BridgedObject


    def generate_doc(self, target_self):
        if target_self is None:
            logger.info("Getting __doc__ for some unknown class")
            return ""
        else:
            logger.info("Getting __doc__ for {}".format(target_self._bridge_repr))

        ty = target_self._bridge_type
        if target_self._bridge_type == 'instancemethod':
            meth_doc = InstanceMethodDoc(target_self)
            return meth_doc.__doc__
        elif ty == "Class":
            class_doc = ClassDoc.from_cls_string(target_self.typeName)
            return class_doc.__doc__
        elif target_self._bridge_type == "reflectedconstructor":
            meth_doc = InstanceMethodDoc(target_self)
            return meth_doc.__doc__
        elif ty.startswith("ghidra"):
            class_doc = ClassDoc.from_cls_string(ty)
            return class_doc.__doc__

        else:
            logger.warning("Unhandled input {}".format(target_self._bridge_repr))

    def generate_module(self, target_self):
        logger.debug("__module__ queried for %s" % target_self._bridge_repr)
        if target_self._bridge_type == "instancemethod":
            full_type =  target_self.im_self._bridge_type
        elif target_self._bridge_type.startswith("ghidra"):
            # On bridged objects _bridge_type should just be what we want
            full_type = target_self._bridge_type
        elif target_self._bridge_type == "javapackage":
            raise AttributeError("javapackage doesn't have __module__")
        # For example: 'ghidra.program.database.ProgramDB'
        return ".".join(full_type.split(".")[:-1])


    def generate_annotations(self, target_self):
        try:
            logger.info("Generating annotations for %s" % target_self._bridge_repr)
            if target_self._bridge_type == "Class":
                meth_doc = InstanceMethodDoc(target_self)
            elif target_self._bridge_type == 'builtin_function_or_method':
                return None
            else:
                meth_doc = InstanceMethodDoc(target_self)
            return meth_doc.get_annotations()
        except Exception as e:
            logger.warning("Got exception %s", e)

    def generate_signature(self, target_self):
        logger.info("Generating signature for %s" % target_self._bridge_repr)
        try:
            if target_self._bridge_type == "Class":
                meth_doc = InstanceMethodDoc(target_self)
            elif target_self._bridge_type == 'builtin_function_or_method':
                return None
            else:
                meth_doc = InstanceMethodDoc(target_self)
            return meth_doc.get_signature()
        except Exception as e:
            logger.warning("Got exception %s", e)

    def generate_objclass(self, target_self):
        x = 1
        return "TEST"



        # setattr(BridgedObject, 'getdoc', __doc__)
        # # setattr(BridgedObject, '__module__', property(__module__))
        # setattr(BridgedCallable, 'getdoc', __doc__)
        #
        # def __subclasses__(target_self):
        #     return []
        #
        # # setattr(BridgedObject, '__subclasses__', __subclasses__)
        # setattr(BridgedCallable, '__annotations__', property(__annotations__))
        # setattr(BridgedCallable, '__signature__', property(__signature__))

        import inspect

        # def isclass(object):
        #     if isinstance(object, BridgedObject):
        #         return object._bridge_type == 'Class'
        #     else:
        #         return isinstance(object, type)
        #
        # setattr(inspect, 'isclass', isclass)

    def intercept_str(self, target_self):
        pass
        raise ConcedeBridgeOverrideException()

    def intercept_init(self, target_self):
        if self.check_for_ipython() and target_self._bridge_type.startswith("ghidra"):
            raise AttributeError()
        raise ConcedeBridgeOverrideException()

    def intercept_call(self, target_self):
        if target_self._bridge_type.startswith("ghidra") or target_self._bridge_type == "Class":
            raise AttributeError()
        raise ConcedeBridgeOverrideException()

    def check_for_ipython(self):
        stack = inspect.stack()
        if stack[3].function == "_info":
            return True
        else:
            return False

    def register_overrides(self):
        jfx_bridge.register_overrides({
            "__module__": self.generate_module,
            "__doc__": self.generate_doc,
            "__objclass__": self.generate_objclass,
            "__annotations__": self.generate_annotations,
            "__signature__": self.generate_signature,
            "__code__": lambda obj: None,
            "__defaults__": lambda obj: None,
            "__kwdefaults__": lambda obj: None,
            "__text_signature__": lambda obj: None,
            "_partialmethod": lambda obj: None,
            "__str__": self.intercept_str,
            "__init__": self.intercept_init,
            "__call__": self.intercept_call
        })


if __name__ == '__main__':
    # p = ClassDoc._get_source_file(currentProgram)
    # c = ClassDoc(currentProgram._bridged_get_type())
    pass