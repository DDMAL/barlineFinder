from django.template import RequestContext
from django.http import HttpResponse
from django.shortcuts import render_to_response
from django.core.files.base import ContentFile

from baragon.models import Page
from baragon.forms import UploadImageForm

import os
from PIL import Image
from StringIO import StringIO

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
            # check uploaded image is a tiff file
            input_file = request.FILES['page_image']
            filename, input_ext = os.path.splitext(input_file.name)
            if input_ext != '.tiff':
                # convert the image to a tiff file
                uploaded_img = Image.open(StringIO(input_file.read()))
                new_filename = '%s.tiff' % filename
                converted_img = StringIO()
                uploaded_img.save(converted_img, 'TIFF')
                page = Page()
                page.image_file.save(new_filename, ContentFile(converted_img.getvalue()), save=True)
            else:
                page = Page(image_file=request.FILES['page_image'])
                page.save()

            # for now, display the database tuple until we figure out what to do with the image
            return HttpResponse('page id: %d, path: %s, height: %d, width: %d' % (page.id, page.image_file, page.height, page.width))
    else:
        # serve the form
        form = UploadImageForm()

    return render_to_response('upload.html', {'form': form}, context_instance=RequestContext(request))
