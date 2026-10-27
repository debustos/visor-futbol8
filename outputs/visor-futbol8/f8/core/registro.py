"""Find what each module declares in f8/<module>/<name>.py, so no shared list has to be edited."""
import importlib,pkgutil
import f8


def declarations(name):
    """Return (package, module) for every f8 subpackage that has <name>.py, in alphabetical order."""
    found=[]
    for info in sorted(pkgutil.iter_modules(f8.__path__),key=lambda i:i.name):
        if not info.ispkg:continue
        target=f'f8.{info.name}.{name}'
        try:found.append((info.name,importlib.import_module(target)))
        except ModuleNotFoundError as error:
            if error.name!=target:raise
    return found
