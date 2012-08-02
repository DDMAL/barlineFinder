from django.db import models

class Page(models.Model):
    image_file = models.ImageField(
        upload_to='images/', 
        height_field='height', 
        width_field='width'
    )
    height = models.IntegerField()
    width = models.IntegerField()
