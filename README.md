# Ghidra IPython


This project is a small IPython extension that uses [ghidra_bridge](https://github.com/justfoxing/ghidra_bridge)
to provide some comfort features for interactive use in IPython.


## Install

Setup the package/extension
```bash
git clone https://github.com/fmagin/ghidra_bridge_ipython
# Install in whatever environment, typically the one you installed ghidra_bridge in
cd ghidra_bridge_ipython
pip install ./
```

You should now be able to start an IPython shell and load the module.
After that your namespace should contain at least contain `_bridge` and possibly the `current*` variables.
```
%load_ext ipyghidra
_bridge
```

To reduce the effort even more:

```bash
ipython profile create ghidra # Creates a profile named 'ghidra'
# Assuming you are still in the git root
cp ipython_config.py $(ipython profile locate ghidra)
```

Now `ipython --profile ghidra` gives you an IPython shell directly that is ready as soon as the prompt appears.

The crucial part of the config is
```python
c.InteractiveShellApp.extensions = ['ipyghidra']
``` 
which loads the module automatically.

The rest are opinionated config decisions that I consider reasonable for a shell that is primarily used to interact with the Ghidra API.



## Features


### Remote Eval Magic

`ghidra_bridge` provides a functionality to evaluate an entire expression on the server side which can massively speedup certain queries.

For example
```python
[ f.name for f in currentProgram.functionManger.getFunctions(True) ]
```
is orders of magnitude slower without this.

In general any time an iterable is returned you are most likely better off just turning this into a list on the server
and getting one response with all the data.

To still get the full comfort of IPython completions the magic `ghidra_eval` handles this.

Line version: 
```python
%ghidra_eval [ f.name for f in currentProgram.functionManger.getFunctions(True) ]
```

Cell version:
```python
%%ghidra_eval
[ f.name for f in currentProgram.functionManger.getFunctions(True) ]
```

In case of a local variable like
```
f = next(currentProgram.functionManager.getFunctions(True))
```
that only exist in the client the following would fail with a naive implementation because `f` is not defined on the server side.
```python
%%ghidra_eval
list(f.parameters)
```
To deal with this the code is parsed using the `ast` module and all variables that exist
in the local namespace are passed to the `remote_eval` call which makes them available on the server side.
So any code that could be run locally should be able to be run on the server.
This includes referencing variables that contain objects that only exist on the client.
Accessing those on the server will force requests over the bridge again which will potentially waste the speed advantage.


`ghidra_eval` only handles _expressions_ so the result has to be accessed via the `_` variable
that references the last cell result or `_$cellnumber` where `$cellnumber` is the number of the cell
the cell in which the command was executed:

```
In [24]: %%ghidra_eval 
    ...: [ f.name for f in fm.getFunctions(True)][:2]                                 
Out[24]: ['entry', 'dealloc']

In [25]: _24                                                                          
Out[25]: ['entry', 'dealloc']
```