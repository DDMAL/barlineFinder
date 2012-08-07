from __future__ import division
from django.template import RequestContext
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response
from django.core.files.base import ContentFile
from django.conf import settings

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
            input_file = request.FILES['page_image']
            filename, input_ext = os.path.splitext(input_file.name)
            uploaded_img = Image.open(StringIO(input_file.read()))

            # create jpeg thumbnail of the uploaded image for efficient display
            thumbnail_img = uploaded_img.copy()
            orig_width, orig_height = uploaded_img.size
            thumbnail_size = (settings.THUMBNAIL_WIDTH, int((settings.THUMBNAIL_WIDTH/orig_width)*orig_height))
            thumbnail_img.thumbnail(thumbnail_size, Image.ANTIALIAS)
            thumbnail_filename = '%s.jpg' % filename
            # convert to jpeg
            thumbnail_jpeg = StringIO()
            thumbnail_img.save(thumbnail_jpeg, 'JPEG')

            page = Page()
            # check uploaded image is a tiff file
            if input_ext != '.tiff':
                # convert the image to a tiff file
                converted_filename = '%s.tiff' % filename
                converted_img = StringIO()
                uploaded_img.save(converted_img, 'TIFF')
                page.image_orig.save(converted_filename, ContentFile(converted_img.getvalue()), save=False)
            else:
                page.image_orig = request.FILES['page_image']

            # add the thumbnail to the model and save
            page.image_thumb.save(thumbnail_filename, ContentFile(thumbnail_jpeg.getvalue()), save=True)

            # redirect to the workbench page
            return HttpResponseRedirect('/workbench/')
    else:
        # serve the form
        form = UploadImageForm()

    return render_to_response('upload.html', {'form': form}, context_instance=RequestContext(request))

def workbench(request):
    page_list = Page.objects.all()

    return render_to_response('workbench.html', {'pages': page_list}, context_instance=RequestContext(request))
