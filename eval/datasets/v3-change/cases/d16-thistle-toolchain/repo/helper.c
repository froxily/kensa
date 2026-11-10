#include <Python.h>

static PyObject *measure(PyObject *self, PyObject *args) {
    return PyLong_FromLong(thistle_width());
}

int thistle_width(void) { return 4; }

static PyMethodDef methods[] = {
    {"measure", measure, METH_NOARGS, NULL},
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef module = {PyModuleDef_HEAD_INIT, "thistle_helper", NULL, -1, methods};
PyMODINIT_FUNC PyInit_thistle_helper(void) { return PyModule_Create(&module); }
