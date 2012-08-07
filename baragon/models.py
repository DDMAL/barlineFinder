from django.db import models

class Page(models.Model):
    image_orig = models.ImageField(
        upload_to='images/', 
        height_field='height', 
        width_field='width'
    )
    image_thumb = models.ImageField(
        upload_to='images/'
    )
    height = models.IntegerField()
    width = models.IntegerField()
