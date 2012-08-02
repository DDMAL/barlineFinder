from django import forms

class UploadImageForm(forms.Form):
    page_image = forms.ImageField(
        label = "Select an image"
    )
