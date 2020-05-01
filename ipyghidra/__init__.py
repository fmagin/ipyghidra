import ast
import inspect
import logging
import os
from typing import Optional

from IPython.core.magic import (Magics, magics_class, line_cell_magic)
import IPython
import ghidra_bridge
from jfx_bridge.bridge import BridgeException

# from ipyghidra.doc_helper import DocHelper
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

    def __init__(self, bridge, **kwargs):
        #super(GhidraBridgeMagics).__init__(kwargs)
        self.bridge = bridge

    @line_cell_magic
    def ghidra_eval(self, line, cell=None):
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
        return self.bridge.bridge.remote_eval(code, **vars)


import subprocess


def terminate_bridge(handle: subprocess.Popen):
    import psutil
    print("Cleaning up ghidra server")

    def on_terminate(proc):
        print("process {} terminated with exit code {}".format(proc, proc.returncode))

    procs = psutil.Process(pid=handle.pid).children()
    for p in procs:
        print(f"Terminating {p}")
        for subproc in psutil.Process(pid=p.pid).children():
            print(f"Terminating {subproc}")
            subproc.terminate()
        p.terminate()
    gone, alive = psutil.wait_procs(procs, timeout=3, callback=on_terminate)
    for p in alive:
        p.kill()


def _setup_bridge(ip) -> Optional[ghidra_bridge.GhidraBridge]:
    from traitlets.config import get_config
    config = get_config()
    try:
        return ghidra_bridge.GhidraBridge(namespace=ip.user_ns, interactive_mode=True)  # creates the bridge and loads the flat API into the global namespace
    except ConnectionRefusedError:
        logging.error("Connection to GhidraBridge server failed")
        bridge_path = f"{os.path.dirname(os.path.dirname(inspect.getfile(ghidra_bridge)))}/ghidra_bridge_server.py"
        pythonRun_path = f"{os.environ['GHIDRA_ROOT'] or '$GHIDRA_ROOT'}/support/pythonRun"
        if config.IPyGhidra and config.IPyGhidra.start_server_if_none and os.environ['GHIDRA_ROOT']:
            logging.warning(f"No server found, starting own with {pythonRun_path} {bridge_path}")
            bridge_process_handle = subprocess.Popen([pythonRun_path, bridge_path], stdout=subprocess.PIPE,
                                                     stderr=subprocess.PIPE)
            ip.push({"bridge_process_handle": bridge_process_handle})
            logging.warning(f"Server started with PID: {bridge_process_handle.pid}")
            line = b""
            while b"serving!" not in line:
                import time
                line = bridge_process_handle.stderr.readline()
                print("Ghidra Server Log: " + line.decode().rstrip())

            import atexit
            atexit.register(terminate_bridge, bridge_process_handle)
            return ghidra_bridge.GhidraBridge(namespace=ip.user_ns, interactive_mode=True)
        else:
            logging.error(f"For a minimal server run  {pythonRun_path} {bridge_path}")




class VarWatcher(object):
    def __init__(self, ip: IPython.InteractiveShell):
        self.ip = ip
        self.last_function = None
        self.last_address = None
    def extra_variables_pre(self):
        program = self.ip.user_ns.get('currentProgram')
        address = self.ip.user_ns.get('currentAddress')
        try:
            function = program.functionManager.getFunctionContaining(address)

        except BridgeException as e:
            logging.warning("Got exception %s while trying to set currentFunction", e)
            function = None
        self.ip.user_ns['currentFunction'] = function
        self.last_address = address
        self.last_function = function

    def extra_variables_post(self):
        program = self.ip.user_ns.get('currentProgram')
        address = self.ip.user_ns.get('currentAddress')
        try:
            function = program.functionManager.getFunctionContaining(address)
            if function != self.last_function:
                pass
            if address != self.last_address:
                pass
        except BridgeException as e:
            logging.warning("Got exception %s while trying to set currentFunction" )


import ipyghidra
def load_ipython_extension(ip: IPython.InteractiveShell):
    logger = logging.getLogger('ipyghidra')
    logger.setLevel(logging.INFO)

    b = _setup_bridge(ip)

    if b:
        logging.info("Connected to bridge")
        ip.push({'_bridge': b})

        logging.info("Registering Magics")
        ip.register_magics(GhidraBridgeMagics(b))

        logging.info("Setting up DocHelper")
        doc_helper = DocHelper(b.bridge)
        ip.push({'_doc_helper': doc_helper})

        logging.info("Patching ghidra_bridge")
        doc_helper.patch_ghidra_bridge()

        var = VarWatcher(ip)
        ip.events.register('pre_run_cell', var.extra_variables_pre)
    else:
        return



