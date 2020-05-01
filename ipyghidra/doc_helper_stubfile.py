import logging
from typing import Optional, List

from jfx_bridge.bridge import BridgedObject, BridgedCallable

from pathlib import Path

from mypy.modulefinder import SearchPaths, FindModuleCache, ModuleNotFoundReason

from distutils.sysconfig import get_python_lib

search_paths = SearchPaths((),(),(get_python_lib(),),())

find_module_cache = FindModuleCache(search_paths)

from typed_ast.ast3 import parse, dump, NodeVisitor, get_docstring

from typed_ast._ast3 import FunctionDef, ClassDef


logging.basicConfig()

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

    def __init__(self, cls: BridgedCallable, cls_string = None):
        # self.cls = cls
        self.cls_string = cls_string or str(cls)[7:-2]
        self._ast = None


    @staticmethod
    def _type_str(bridged_obj: BridgedObject):
        _t = bridged_obj._bridged_get_type()  # "<type 'ghidra.program.database.ProgramDB'>"
        return str(_t)[7:-2]  # 'ghidra.program.database.ProgramDB'

    @property
    def functions(self):
        ff = FuncDefFinder()
        ff.visit(self.ast)
        return ff.functions

    @property
    def __doc__(self):
        ast = self.ast
        doc = get_docstring(ast)
        return doc

    @property
    def ast(self) -> ClassDef:
        if not self._ast:
            source = self.source_file.read_text()
            file_ast = parse(source, self.source_file)
            cf = ClassFinder()
            cf.visit(file_ast)
            self._ast = cf.classes[0]
        return self._ast


    @property
    def source_file(self) -> Path:

        result = find_module_cache.find_module(self.cls_string)
        if isinstance(result, str):
            return Path(result)
        elif isinstance(result, ModuleNotFoundReason):
            raise ValueError(result)




class InstanceMethodDoc(BaseDoc):

    def __init__(self, bridged_callable: BridgedCallable):
        try:
            self.cls_doc = ClassDoc(bridged_callable.im_class)
        except:
            self.cls_doc = ClassDoc(None, cls_string=bridged_callable.__name__)
        self.name = bridged_callable.__name__
        self._asts: Optional[FunctionDef] = None


    @property
    def is_constructor(self):
        return self.name == self.cls_doc.cls_string

    @property
    def possible_asts(self) -> List[FunctionDef]:
        name = "__init__" if self.is_constructor else self.name
        if not self._asts:
            self._asts = list(filter(lambda f: f.name == name, self.cls_doc.functions))

        return self._asts

    @property
    def overloaded(self) -> bool:
        return len(self.possible_asts) > 1

    @property
    def ast(self) -> Optional[FunctionDef]:
        if not self.overloaded:
            return self.possible_asts[0]
        else:
            return None

    @property
    def __doc__(self) -> str:
        if not self.overloaded:
            return get_docstring(self.ast)

class DocHelper():
    def __init__(self, bridge):
        self.bridge = bridge
    pass

    def patch_ghidra_bridge(self):
        from jfx_bridge.bridge import BridgedCallable, BridgedObject

        def __signature__(target_self):
            return self.get_signature(target_self)

        def __annotations__(target_self):
            return self.get_annotations(target_self)

        def __doc__(target_self=None):
            if target_self is None:
                logger.info("Getting __doc__ for some unknown class")
                return ""
            else:
                logger.info("Getting __doc__ for {}".format(repr(target_self)))

            ty = target_self._bridged_get_type()
            if str(ty) == "<type 'instancemethod'>":
                meth_doc = InstanceMethodDoc(target_self)
                return meth_doc.__doc__
            elif str(ty) == "<type 'builtin_function_or_method'>":
                return ""
            elif target_self._bridge_type == "Class" and str(ty) == "<type 'java.lang.Class'>":
                class_doc = ClassDoc(target_self)
                return class_doc.__doc__
            elif target_self._bridge_type == "reflectedconstructor":
                meth_doc = InstanceMethodDoc(target_self)
                return meth_doc.__doc__
            elif ty._bridge_type == "Class":
                class_doc = ClassDoc(ty)
                return class_doc.__doc__

            else:
                logging.warning("Unhandled input {}".format(target_self))


        setattr(BridgedObject, 'getdoc', __doc__)
        setattr(BridgedCallable, 'getdoc', __doc__)

        def __subclasses__(target_self):
            return []

        # setattr(BridgedObject, '__subclasses__', __subclasses__)
        setattr(BridgedCallable, '__annotations__', property(__annotations__))
        setattr(BridgedCallable, '__signature__', property(__signature__))

        import inspect

        # def isclass(object):
        #     if isinstance(object, BridgedObject):
        #         return object._bridge_type == 'Class'
        #     else:
        #         return isinstance(object, type)
        #
        # setattr(inspect, 'isclass', isclass)


if __name__ == '__main__':
    # p = ClassDoc._get_source_file(currentProgram)
    c = ClassDoc(currentProgram._bridged_get_type())
    pass