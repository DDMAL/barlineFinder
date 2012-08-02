from django.template import RequestContext
from django.http import HttpResponse
from django.shortcuts import render_to_response

from baragon.models import Page
from baragon.forms import UploadImageForm

def home(request):
    '''
    Serve the home page
    '''

    return render_to_response('index.html', context_instance=RequestContext(request))

def upload(request):
    '''
    Upload an image of a musical document
    '''

    if request.method == 'POST':
        # bind the data to the form
        form = UploadImageForm(request.POST, request.FILES)
        if form.is_valid():
            page = Page(image_file=request.FILES['page_image'])
            page.save()
            # for now, display the database tuple until we figure out what to do with the image
            return HttpResponse('page id: %d, path: %s, height: %d, width: %d' % (page.id, page.image_file, page.height, page.width))
    else:
        # serve the form
        form = UploadImageForm()

    return render_to_response('upload.html', {'form': form}, context_instance=RequestContext(request))
