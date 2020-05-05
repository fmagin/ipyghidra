import logging
import sys

import nose
from ipyghidra.doc_helper_stubfile import DocHelper
from IPython.core import oinspect

import ghidra_bridge

# Otherwise the test framework searches the entire ghidra namespace for test functions
bridge_namespace = {}
b = ghidra_bridge.GhidraBridge(namespace=bridge_namespace)

bridge_logger = b.bridge.logger

bridge_logger.addHandler(logging.StreamHandler())
doc_helper = DocHelper(b)
doc_helper.register_overrides()


inspector = oinspect.Inspector()


def test_currentProgram():
    result = inspector.info(bridge_namespace["currentProgram"])
    expected = {
        'type_name': 'BridgedObject',
        'base_class': "<class 'jfx_bridge.bridge.BridgedObject'>",
        # 'string_form': 'dkacstm-lan-3_3_6.elf - .ProgramDB',
        'namespace': None,
        'length': None,
        # 'file': '~/gits/jfx_bridge/jfx_bridge/bridge.py',
        'definition': None,
        'docstring': 'Database implementation for Program.',
        'source': None,
        'init_definition': None,
        'class_docstring': 'An object you can only interact with on the opposite side of a bridge ',
        'init_docstring': None,
        # 'init_docstring': "ghidra.program.database.ProgramDB() has multiple implementations, not handled yet",
        'call_def': None,
        'call_docstring': None,
        'ismagic': False,
        'isalias': False,
        'isclass': None,
        'found': True,
        'name': '',
        'subclasses': None
    }
    nose.tools.assert_dict_contains_subset(expected, result)


def test_functionManager():
    expected = {'type_name': 'BridgedObject',
                'base_class': "<class 'jfx_bridge.bridge.BridgedObject'>",
                # 'string_form': 'ghidra.program.database.function.FunctionManagerDB@155cc851',
                'namespace': None,
                'length': None,
                # 'file': '~/gits/jfx_bridge/jfx_bridge/bridge.py',
                'definition': None,
                'docstring': 'Class that manages all functions within the program; there are some\n'
                             'convenience methods on Listing to create and access functions, but\n'
                             'all function related calls are routed to this class.',
                'source': None,
                'init_definition': None,
                'class_docstring': 'An object you can only interact with on the opposite side of a bridge ',
                # 'init_docstring': "Construct a new FunctionManager\n"
                #                   "@param dbHandle data base handle\n"
                #                   "@param addrMap address map for the program\n"
                #                   "@param openMode CREATE, UPDATE, READ_ONLY, or UPGRADE defined in\n"
                #                   " db.DBConstants\n"
                #                   "@param lock the program synchronization lock\n"
                #                   "@param monitor\n"
                #                   "@throws VersionException if function manager's version does not match\n"
                #                   " its expected version\n"
                #                   "@throws CancelledException if the function table is being upgraded\n"
                #                   " and the user canceled the upgrade process\n"
                #                   "@throws IOException if there was a problem accessing the database",
                'init_docstring': None,
                'call_def': None,
                'call_docstring': None,
                'ismagic': False,
                'isalias': False,
                'isclass': None,
                'found': True,
                'name': '',
                'subclasses': None}

    result = inspector.info(bridge_namespace["currentProgram"].functionManager)
    nose.tools.assert_dict_contains_subset(expected, result)


def test_functionManager_getFunctionAt():
    expected = {'type_name': 'BridgedCallable',
                'base_class': "<class 'jfx_bridge.bridge.BridgedCallable'>",
                # 'string_form': '<bound method ghidra.program.database.function.FunctionManagerDB.getFunctionAt of ghidra.program.database.function.FunctionManagerDB@155cc851>',
                'namespace': None,
                'length': None,
                # 'file': '~/gits/jfx_bridge/jfx_bridge/bridge.py',
                'definition': "(self: None, entryPoint: 'ghidra.program.model.address.Address') -> "
                              "'ghidra.program.model.listing.Function'",
                'docstring': 'NO JAVADOC AVAILABLE',
                'source': None,
                'init_definition': None,
                'class_docstring': 'An object you can only interact with on the opposite side of a bridge ',
                'init_docstring': None,
                'call_def': None,
                'call_docstring': None,
                'ismagic': False,
                'isalias': False,
                'isclass': None,
                'found': True,
                'name': '',
                'subclasses': None}

    result = inspector.info(bridge_namespace["currentProgram"].functionManager.getFunctionAt)

    nose.tools.assert_dict_contains_subset(expected, result)


def test_class_with_multiple_constructors():
    expected = {'type_name': 'BridgedType',
                'base_class': "<class 'jfx_bridge.bridge.BridgedType'>",
                'string_form': "<type 'ghidra.GhidraApplicationLayout'>",
                'namespace': None,
                'length': None,
                # 'file': '~/gits/jfx_bridge/jfx_bridge/bridge.py',
                'definition': None,
                'docstring': "The Ghidra application layout defines the customizable elements of the Ghidra\n"
                             "application's directory structure.",
                'source': None,
                'init_definition': None,
                'class_docstring': 'An object you can only interact with on the opposite side of a bridge ',
                'init_docstring': 'ghidra.GhidraApplicationLayout() has multiple implementations, not handled yet',
                'call_def': None,
                'call_docstring': None,
                'ismagic': False,
                'isalias': False,
                'isclass': None,
                'found': True,
                'name': '',
                'subclasses': None}

    result = inspector.info(bridge_namespace['ghidra'].GhidraApplicationLayout)
    nose.tools.assert_dict_contains_subset(expected, result)


def test_class_with_unique_constructor():
    expected = {'type_name': 'BridgedType',
                'base_class': "<class 'jfx_bridge.bridge.BridgedType'>",
                'string_form': "<type 'ghidra.app.util.cparser.C.CompositeHandler'>",
                'namespace': None,
                'length': None,
                'file': '~/gits/jfx_bridge/jfx_bridge/bridge.py',
                'definition': "(self: None, parent: 'ghidra.program.model.data.Composite') -> None",
                'docstring': 'Used by the CParser to handle fields added to structures(composites).\n'
                             'Currently only bitfields are handled specially.\n\n'
                             'NOTE: when bitfield handling is added directly to structures, this class may\n'
                             'no longer be necessary.',
                'source': None,
                'init_definition': None,
                'class_docstring': 'An object you can only interact with on the opposite side of a bridge ',
                'init_docstring': 'NO JAVADOC AVAILABLE',
                'call_def': None,
                'call_docstring': None,
                'ismagic': False,
                'isalias': False,
                'isclass': None,
                'found': True,
                'name': '',
                'subclasses': None}

    result = inspector.info(bridge_namespace['ghidra'].app.util.cparser.C.CompositeHandler)

    nose.tools.assert_dict_contains_subset(expected, result)


def test_constructor_mess():
    cls = bridge_namespace['ghidra'].GhidraApplicationLayout

    result = inspector.info(cls.__init__)

def test_module_on_object():
    nose.tools.assert_equal(bridge_namespace["currentProgram"].__module__, "ghidra.program.database")

def test_module_on_instance_method():
    nose.tools.assert_equal(bridge_namespace["currentProgram"].getFunctionManager.__module__, "ghidra.program.database")