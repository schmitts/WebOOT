from cStringIO import StringIO
from contextlib import contextmanager
from os.path import exists, join as pjoin
from subprocess import Popen, PIPE
from tempfile import NamedTemporaryFile
from thread import get_ident

from pyramid.httpexceptions import HTTPFound, HTTPNotFound
from pyramid.location import lineage
from pyramid.response import Response
from pyramid.url import static_url
from pyramid.view import view_config

import ROOT as R

from .utils import fixup_hist_units

from .resources.multitraverser import MultipleTraverser
from .resources.filesystem import FilesystemTraverser
from .resources.root.file import RootFileTraverser
from .resources.root.object import RootObject

def my_view(request):
    
    return {'project':'WebOOT'}

def build_draw_params(h, params):
    options = ["colz" if isinstance(h, R.TH2) else "box"]
    if "hist" in params:
        options.append("hist")
    if "e0x0" in params:
        options.append("e0x0")
    return " ".join(options)

def convert_eps(input_name, resolution=100, target_type="png"):
    with NamedTemporaryFile(suffix=".png") as tmpfile:
        p = Popen(["convert", "-density", str(resolution), input_name, tmpfile.name])
        p.wait()
        with open(tmpfile.name) as fd:
            content = fd.read()
    
    return content

@contextmanager
def render_canvas(resolution=100, target_type="png"):
    # We need a thread-specific name, otherwise if two canvases exist with the
    # same name we can get crash
    canvas_name = str(get_ident())
    assert not R.gROOT.GetListOfCanvases().FindObject(canvas_name), (
        "Canvas collision")
    
    c = R.TCanvas(canvas_name)
    def f():
        with NamedTemporaryFile(suffix=".eps") as tmpfile:
            c.SaveAs(tmpfile.name)
            if target_type == "eps":
                content = open(tmpfile.name).read()
            else:
                content = convert_eps(tmpfile.name, resolution, target_type)
        return Response(content, content_type="image/{0}".format(target_type))
            
    c._weboot_canvas_to_response = f
    yield c    

def render_histogram(context, request):
    h = context.obj
    if not isinstance(h, R.TH1):
        raise HTTPNotFound("Not a histogram")
    
    print "Will attempt to render", h
        
    if "unit_fixup" in request.params:
        h = fixup_hist_units(h)
    
    if "nostat" in request.params:
        h.SetStats(False)
    
    if "notitle" in request.params:
        h.SetTitle("")
    
    with render_canvas(min(request.params.get("resolution", 100), 200)) as c:
        if "logx" in request.params: c.SetLogx()
        if "logy" in request.params: c.SetLogy()
        if "logz" in request.params: c.SetLogz()
        
        h.Draw(build_draw_params(h, request.params))
        
        return c._weboot_canvas_to_response()

def view_root_object_render(context, request):
    print "I am inside view_roto-object_render:", context, context.o
    if issubclass(context.cls, R.TH1):
        return render_histogram(context, request)
    return HTTPFound(location=static_url('weboot:static/close_32.png', request))
    
def build_path(context):
    return "".join('<span class="breadcrumb">{0}</span>'.format(l.__name__) 
                    for l in reversed(list(lineage(context))) if l.__name__)

def view_root_object(context, request):
    if context.forward_url:
        return HTTPFound(location=context.forward_url)
    return dict(path=build_path(context),
                content="\n".join(context.content))

def view_multitraverse(context, request):
    content = []
    for name, finalcontext in context.contexts:
        content.append("<p>{0} -- {1.url}</p>".format(name, finalcontext))
    return dict(path='You are at {0!r} {1!r} <a href="{2}/?render">Render Me</a>'.format(context.path, context, context.url),
                content="\n".join(content))

def view_multitraverse_render(context, request):
    return Response("Hello, world", content_type="text/plain")

#@view_config(renderer='weboot:templates/result.pt', context=RootFileTraverser)
#def view_rootfile(context, request):
#    return dict(path="You are at {0}".format(context.path),
#                content=context.content)
    
#@view_config(renderer='weboot:templates/result.pt', context=FilesystemTraverser)
def view_listing(context, request):
    sections = {}
    for item in context.items:
        sections.setdefault(item.section, []).append(item)
    for items in sections.values():
        items.sort(key=lambda o: o.name)
    section_list = []
    #fsorted(sections.iteritems())
    for sec in ["root_file", "directory", "hist"]:
        if sec in sections:
            section_list.append((sec, sections.pop(sec)))
    section_list.extend(sections.iteritems())
    
    return dict(path=build_path(context), 
                context=context,
                sections=section_list)
