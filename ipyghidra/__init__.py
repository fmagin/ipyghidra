
from IPython.core.magic import (Magics, magics_class, line_cell_magic, line_magic)

import ast


import ghidra_bridge
import logging

from ipyghidra.doc_helper import DocHelper

b = None


class VarVisitor(ast.NodeVisitor):
    """
    Simple visitor that gathers all variable names from an AST
    """
    def __init__(self):
        super(VarVisitor, self).__init__()
        self.variables = set()

    def visit_Name(self, node):
        self.variables.add(node.id)



@magics_class
class GhidraBridgeMagics(Magics):

    @line_cell_magic
    def ghidra_eval(self, line, cell=None):
        b = self.shell.user_ns['_bridge'] # type: ghidra_bridge.ghidra_bridge.GhidraBridge
        # Of the cell is not none use it and ignore the line, otherwise use the line
        if cell:
            code = cell
        elif line:
            code = line
        else:
            # Neither cell nor line was given, i.e. just `%ghidra_eval`. Run the last cell via the bridge
            code = self.shell.user_ns['In'][-2]
        # Parse the AST and gather all variable names used
        code_ast = ast.parse(code)
        v = VarVisitor()
        v.visit(code_ast)
        # For every variable in the AST check if it is defined in the current user namespace and if yes get its actual value
        vars = {var: self.shell.user_ns[var] for var in  v.variables if var in self.shell.user_ns}
        # This mapping from variable names to objects can now be passed to remote_eval which makes sure those variables exist when evaluating on the server side
        return b.bridge.remote_eval(code, **vars)


def load_ipython_extension(ip):
    global b
    import ghidra_bridge
    logger = logging.getLogger('ipyghidra')
    logger.setLevel(logging.INFO)
    try:
        b = ghidra_bridge.GhidraBridge(namespace=ip.user_ns, interactive_mode=True) # creates the bridge and loads the flat API into the global namespace
    except ConnectionRefusedError:
        logging.error("Connection to GhidraBridge server failed")
        try:
            import os
            import inspect
            bridge_path = os.path.dirname(os.path.dirname(inspect.getfile(ghidra_bridge)))
            logging.error("For a minimal server run $GHIDRA_ROOT/support/pythonRun %s/ghidra_bridge_server.py" % bridge_path)
        except:
            pass
    logger.info("Connected to bridge")
    ip.user_ns.update({'_bridge': b})
    logger.info("Registering Magics")
    ip.register_magics(GhidraBridgeMagics)
    logger.info("Setting up DocHelper")
    doc_helper = DocHelper(b.bridge)
    ip.user_ns.update({'_doc_helper': doc_helper})
    logger.info("Patching ghidra_bridge")
    doc_helper.patch_ghidra_bridge()


