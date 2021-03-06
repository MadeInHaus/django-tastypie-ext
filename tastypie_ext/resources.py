import sys

from django.contrib.auth.models import User          
from django.conf.urls.defaults import url

from tastypie import http
from tastypie import fields
from tastypie.utils import trailing_slash
from tastypie.resources import ModelResource, Resource
from tastypie.exceptions import ImmediateHttpResponse
from tastypie.authentication import BasicAuthentication
from tastypie.authorization import Authorization, ReadOnlyAuthorization, DjangoAuthorization

# These are based on the tastypie fork
from tastypie.models import ApiKey
from tastypie.authentication import ApiKeyAuthentication

import tastypie_ext.settings as settings 
from tastypie_ext.authentication import FacebookOAUTH2Authentication

class UserResource(ModelResource):
    """
    Resource to represent an API User.
    Used e.g for authentication. This implementation
    relies on django's inbuilt User model from the `contrib.auth` package.
    
    """
    
    class Meta:
        queryset = User.objects.all()
        resource_name = 'user'
        
        fields = settings.TASTYPIE_EXT_USERRESOURCE_FIELDS
        allowed_methods = ['get']
        include_resource_uri = False        
        authentication = ApiKeyAuthentication()
        authorization = ReadOnlyAuthorization()
        
        
class SessionResource(ModelResource):
    """Represent a (active) session.
    Can be used to fetch current user associated
    with session, as well as destroy session (e.g invalidate session token)
    using an HTTP DELETE on the resource URI.
    
    """
    user = fields.ToOneField(
        'tastypie_ext.resources.UserResource', 'user', full=True)

    class Meta(object):
        queryset = ApiKey.objects.all()
        resource_name = 'sessions'
        fields = ['user', 'key']
        allowed_methods = ['get', 'delete']
        authorization = Authorization()
        authentication = ApiKeyAuthentication()
        always_return_data = True
        
        
class POSTAPIKeyAuthenticationResource(ModelResource):
    """
    HTTP POST-based authentication end point
    for use with the ApiKeyAuthentication 
    flow.
    
    """
    
    user = fields.ToOneField(
        'tastypie_ext.resources.UserResource', 'user', full=True)

    class Meta(object):
        queryset = ApiKey.objects.all()
        resource_name = 'authenticate'
        fields = ['user', 'key']
        allowed_methods = ['post']
        authorization = Authorization()
        authentication = BasicAuthentication()
        include_resource_uri = False
        always_return_data = True

    def obj_create(self, bundle, request=None, **kwargs):
        "Get or Create a new key for the session."
        bundle.obj, _created = ApiKey.objects.get_or_create(user=request.user)
        return bundle

    def dehydrate_resource_uri(self, bundle):
        return SessionResource().get_resource_uri(bundle.obj)



class GETAPIKeyAuthenticationResource(ModelResource):
    """
    HTTP GET-based authentication end point
    for use with the ApiKeyAuthentication
    flow. This allows to use this with cross-domain
    AJAX (e.g JSONP).
    
    """
    
    user = fields.ToOneField(
        'tastypie_ext.resources.UserResource', 'user', full=True)
    
    class Meta(object):
        queryset = ApiKey.objects.all()
        resource_name = 'authenticate'
        fields = ['user', 'key']
        allowed_methods = ['get']
        include_resource_uri = False        
        authorization = Authorization()
        authentication = BasicAuthentication()
        
    def override_urls(self):
        """We override this to change default behavior
        for the API when using GET to actually "get or create" a resource,
        in this case a new session/key."""
        
        return [
            url(r"^(?P<resource_name>%s)%s$" % (self._meta.resource_name, trailing_slash()), 
                self.wrap_view('_create_key'), name="api_get_key"),
            ]
  
    def _create_key(self, request, **kwargs):
        """Validate using BasicAuthentication, and get or create Api Key
        if authenticated"""

        self.method_check(request, allowed=['get'])
        self.is_authenticated(request)
        self.throttle_check(request)
        
        bundle = self.build_bundle(obj=None, request=request)
        bundle = self.obj_create(bundle, request, **kwargs)
        bundle = self.full_dehydrate(bundle)

	#changing name for consistency with TastyPie 'api_key' params
	bundle.data['api_key'] = bundle.data['key']
	del bundle.data['key']

        self.log_throttled_access(request)
        return self.create_response(request, bundle.data)
    
        
    def obj_create(self, bundle, request=None, **kwargs):
        """Get or Create a new key for the session"""
        bundle.obj, _created = ApiKey.objects.get_or_create(user=request.user)
        return bundle
    
    def obj_get(self, request=None, **kwargs):
        raise ImmediateHttpResponse(response=http.HttpUnauthorized())
    
    def obj_get_list(self, request=None, **kwargs):
        raise ImmediateHttpResponse(response=http.HttpUnauthorized())

        
class GETAPIFacebookTokenAuthenticationResource(GETAPIKeyAuthenticationResource):
    """
    Uses Django-facebook to perform OAuth 2.0 authentication with facebook,
    and, if successful, issue own api session key.
    
    Typical use case is with a mobile client e.g:
    1. Mobile client app performs facebook authentication, gets key from fb
    2. Mobile client app hits this authentication url with the fb key
    3. API backend (this resource) validates the facebook key server-side
    4. if successful, API backend (this resource) authenticates user and
       returns own key for use in rest of session, as well storing
       the fb key as needed for further actions
      
       
    * It is required that the user's email be available, e.g the access key
      that is generated should have the 'email' access permission. See Facebook's
      Graph API documentation for more information.
       
    References:
    [1] http://stackoverflow.com/questions/4623974/
    [2] https://developers.facebook.com/docs/authentication/client-side/

    """

    class Meta(object):
        queryset = ApiKey.objects.all()
        resource_name = 'fb_authenticate'
        fields = ['user', 'key']
        include_resource_uri = False        
        allowed_methods = ['get']
        authorization = Authorization()
        authentication = FacebookOAUTH2Authentication()
         
