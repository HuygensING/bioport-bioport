
import grok
import sys
from BioPortRepository.repository import Repository
import BioPortRepository
from BioPortRepository.common import  BioPortException
from NamenIndex.common import to_ymd, from_ymd
from NamenIndex.naam import Naam
from common import RepositoryInterface, format_date, format_dates, format_number
from zope.interface import Interface
from zope import schema
import app
from permissions import *
from z3c.batching.batch import  Batch

from zope.session.interfaces import ISession

class IAdminSettings(Interface):           
    SVN_REPOSITORY = schema.TextLine(title=u'URL of svn repository', required=False)
    SVN_REPOSITORY_LOCAL_COPY = schema.TextLine(title=u'path to local copy of svn repository', required=False)
   
    DB_CONNECTION = schema.TextLine(title=u'Database connection (e.g. "mysql://root@localhost/bioport_test" )', required=False)
    LIMIT = schema.Decimal(title=u'Dont download more than this amount of biographies per source (used for testing)', required=False)

    
class Admin(grok.Container,  RepositoryInterface):
    grok.implements(IAdminSettings)
    grok.template('admin_index')
    
    SVN_REPOSITORY = None
    SVN_REPOSITORY_LOCAL_COPY = None
    DB_CONNECTION = None
    LIMIT = None
    
    def get_repository(self):
        try:
            return self._repo
        except:
            self._repo = Repository(
	            svn_repository=self.SVN_REPOSITORY, 
	            svn_repository_local_copy=self.SVN_REPOSITORY_LOCAL_COPY,
	            db_connection=self.DB_CONNECTION,
	            ZOPE_SESSIONS=False, #use z3c.saconfig package
	        ) 
	    return self._repo

    def __getstate__(self):
        #we cannot (And dont want to) pickle the repository -- like this we exclude it
        del self.__dict__['_repo']
        return self.__dict__
    def repository(self):
        return self.get_repository()
    
    def format_date(self, s):
        return format_date(s)
    
    def format_dates(self, s1, s2):
        return  format_dates(s1, s2)
    
    def format_number(self, s):
        return format_number(s)
    
class Edit(grok.EditForm):
    grok.template('edit')
    grok.context(Admin)
    form_fields = grok.Fields(IAdminSettings)
    @grok.action(u"Edit Admin settings", name="edit_settings")
    def edit_admin(self, **data):
        self.applyData(self.context, **data)
        self.context.get_repository().db.metadata.create_all()
        self.redirect(self.url(self))
    
#    @grok.action('reset database (LOOK OUT)', name="reset_database")
#    def reset_database(self, **data):
#        self.context.get_repository().db.metadata.drop_all()
#        self.context.get_repository().db.metadata.create_all()
#        self.redirect(self.url(self))
        
    @grok.action('Fill the similarity Cache', name='fill_similarity_cache') 
    def fill_similarity_cache(self, **data):
        self.context.repository().db.fill_similarity_cache()
        self.redirect(self.url(self))
       
       
    @grok.action('Refresh the similar persons cache')
    def fill_most_similar_persons_cache(self, **data):
        self.context.repository().db.fill_most_similar_persons_cache(refresh=True)
        self.redirect(self.url(self))
        
        
    @grok.action('Create non-existing tables')
    def reset_database(self, **data):
        self.context.get_repository().db.metadata.create_all()
        self.redirect(self.url(self))
        
    @grok.action('Refresh the similarity cache [I.E. EMPTYING IT FIRST]')
    def refresh_similirity_cache(self, **data): 
        self.context.repository().db.fill_similarity_cache(refresh=True)
        self.redirect(self.url(self))
        
    @grok.action('Fill geolocations table')
    def fill_geolocations_table(self, **data): 
        self.context.repository().db._update_geolocations_table()
        self.redirect(self.url(self))
        
    @grok.action('Fill occupations table')
    def fill_occupations_table(self, **data): 
        self.context.repository().db._update_occupations_table()
        self.redirect(self.url(self))
        
    @grok.action('Set state of edited persons to bewerkte(JG: DELETE THIS BUTTON WHEN DONE)')
    def set_state_to_bewerkt(self, **data):
        from BioPortRepository.upgrade import upgrade_persons
        upgrade_persons(self.context.repository())
class Display(grok.DisplayForm):
    grok.context(Admin)
    form_fields = grok.Fields(IAdminSettings)
 
class Index(grok.View):
    pass
    
class Biographies(grok.View):
    grok.context(Admin)
    
    def get_biographies(self):
        return self.context.get_repository().get_biographies()


class Biography(grok.View):
    pass


class Persons(app.Personen):
    def get_status_values(self, k=None):
        return self.context.repository().get_status_values(k)
    
class Source(grok.EditForm):
    def get_repository(self):
        repository = self.context.repository()
        return repository
    
    def update(self, source_id=None, description=None, url=None, quality=None):
        if source_id:
            repository = self.get_repository()
            source = repository.get_source(source_id) 
            if url is not None:
                source.set_value(url=url)
            if description is not None:
                source.set_value(description=description) 
            if quality is not None:
                source.set_quality(int(quality))
    
            repository.save_source(source)
            
            msg = 'Changed source %s' % source.id
            print msg
            
        
               
class Sources(grok.View):
    

    def update(self, action=None, source_id=None, url=None, description=None):
        if action == 'update_source':
            self.update_source(source_id)
            self.redirect(self.url())
        elif action == 'source_delete':
            self.source_delete(source_id)
        elif action=='add_source':
            self.add_source(source_id, url, description)   
            
    def update_source(self, source_id):
        repo = self.context.repository()
        source =repo.get_source(source_id)
        repo.update_source(source, limit=int(self.context.LIMIT))
        
    def download_data(self, source_id):
        repository = self.context.repository()
        source = repository.get_source(id=source_id)
        repository.download_biographies(source=source)
        self.redirect(self.url())
    def add_source(self, source_id, url, description=None):
        source = self.context.repository().add_source(BioPortRepository.source.Source(source_id, url, description))
 
    def source_delete(self, source_id):
        repo = self.context.repository() 
        source = self.context.repository().get_source(source_id)
        repo.commit(source)
        repo.delete_source(source)
        
        msg = 'Deleted source with id %s ' % source_id
        print msg
        return msg
    
class MostSimilar(grok.Form):
    #grok.require('bioport.EditRepository')
    def update(self):
        self.start = int(self.request.get('start', 0))
        self.size = int(self.request.get('size', 20))
        self.similar_to = self.request.get('similar_to', None)
        self.redirect_to = None
        self.most_similar_persons = self.context.repository().get_most_similar_persons(start=self.start, size=self.size, similar_to = self.similar_to)
    def goback(self,  data = None):
        redirect_url = self.url(data=data)
        if self.redirect_to:
            redirect_url = '?'.join([self.redirect_to, redirect_url.split('?')[1]])
            
        self.redirect(redirect_url) 
    @grok.action('identificeer', name='identify')
    def identify(self):
        bioport_ids = self.request.get('bioport_ids')
        repo = self.context.repository()
        persons = [BioPortRepository.person.Person(id, repository=repo) for id in bioport_ids]
        assert len(persons) == 2
        repo.identify(persons[0], persons[1])
        
        self.bioport_ids = bioport_ids
        self.persons = persons
        msg = 'Identified <a href="../persoon?bioport_id=%s">%s</a> and <a href="../persoon?bioport_id=%s">%s</a>' % (
                     bioport_ids[0],  bioport_ids[0], bioport_ids[1],  bioport_ids[1])
        
        #redirect the user to where wer were
        data={'msg':msg, 'start':self.request.get('start', 0)}
#        request.form.set('msg', msg)
        self.goback(data = data)
        
    @grok.action('anti-identificeer', name='antiidentify')
    def antiidentify(self):
        bioport_ids = self.request.get('bioport_ids')
        repo = self.context.repository()
        persons = [BioPortRepository.person.Person(id, repository=repo) for id in bioport_ids]
        p1, p2 = persons
        repo.antiidentify(p1, p2)
        
        self.bioport_ids = bioport_ids
        self.persons = persons
        msg = 'Anti-Identified <a href="../persoon?bioport_id=%s">%s</a> and <a href="../persoon?bioport_id=%s">%s</a>' % (
                     bioport_ids[0], persons[0].get_bioport_id(), bioport_ids[1], persons[1].get_bioport_id())
        
        #redirect the user to where wer were
        data={'msg':msg, 'start':self.request.get('start', 0)}
#        request.form.set('msg', msg)
        self.goback(data = data)
        
   
    @grok.action('Moeilijk geval', name='deferidentification')
    def deferidentification(self):
        bioport_ids = self.request.get('bioport_ids') 
        repo = self.context.repository()
        persons = [BioPortRepository.person.Person(id, repository=repo) for id in bioport_ids]
        p1, p2 = persons
        repo.defer_identification(p1, p2)
        
        self.bioport_ids = bioport_ids
        self.persons = persons
        msg = '<a href="../persoon?bioport_id=%s">%s</a> and <a href="../persoon?bioport_id=%s">%s</a> in de lijst met moeilijke gevallen gezet' % (
                     bioport_ids[0], persons[0].get_bioport_id(), bioport_ids[1], persons[1].get_bioport_id())
        
        #redirect the user to where wer were
        data={'msg':msg, 'start':self.request.get('start', 0)}
        self.goback( data = data)
             
    @grok.action('zoek', name="search_persons")
    def search_persons(self):
        self.persons = self.get_persons()
        
    @grok.action('similar persons', name='similar_persons')
    def similar_persons(self):
        self.request.form['search_term'] = '' 
        self.update()
        if len(self.selected_persons) == 1:
            person = self.selected_persons[0]
            ls = self.context.repository().get_most_similar_persons(similar_to=person.bioport_id)
            def other_person(i):
                score, p1, p2 = i
                if person.bioport_id == p1.bioport_id:
                    return p2
                else:
                    return p1
            ls = map(other_person, ls)
#            ls = []
#            ls += [p2 for score, p1, p2 in qry_result if p1.bioport_id == person.bioport_id]   
#            ls += [p1 for score, p1, p2 in qry_result if p2.bioport_id == person.bioport_id]   
            
            batch = Batch(ls, start=self.batch_start, size=self.batch_size)
            self.persons = batch 
            self.persons.grand_total = len(ls)

class Persoon(app.Persoon, grok.EditForm):
    """This should really be an "Edit" view on a "Person" Model
    
    But I am in an incredible hurry and have no time to learn :-("""
   
    def update(self, **args):
        self.bioport_id = self.request.get('bioport_id')         
        if not self.bioport_id:
            #XXX make a userfrienlider error
            assert 0, 'need bioport_id in the request'
            
        self.repository = self.context.repository()
        self.person  = self.repository.get_person(bioport_id=self.bioport_id)  
        self.bioport_biography =  self.repository.get_bioport_biography(self.person) 
        self.merged_biography  = self.person.get_merged_biography()

        self.occupations = self.get_states(type='occupation')
        self.occupations_with_id = [s for s in self.occupations if s.idno]
        
        self.history_counter = 1
        http_referer = self.request.get('HTTP_REFERER', '')
        http_referer = http_referer.split('?')[0]
        http_referer = http_referer.split('/')
        if 'persoon' in http_referer or 'changename' in http_referer: 
	        self.history_counter = self.session_get('history_counter', 1) + 1
        self.session_set('history_counter', self.history_counter)
        
        
    def session_get(self, k, default=None): 
        return ISession(self.request)['bioport'].get(k, default)
    
    def session_set(self, k, v):
        ISession(self.request)['bioport'][k] = v
    def title(self):
        n = self.person.naam()
        if n:
            return n.volledige_naam()
        else:
            return '' 

    def url(self, object=None, name=None, data=None, hash=None):
        url = app.Persoon.url(self, object, name, data)
        if hash:
            if '?' in url: 
                url = url.replace('?', '#%s?' % hash)
            else:
                url = '%s#%s' % (url, hash)
        return url
    
        
    def sex_options(self):
        return [('1', 'man'), ('2', 'vrouw'), ('0', 'onbekend')]
    
    def to_ymd(self, s):
        return to_ymd(s)
    
    def get_bioport_namen(self):
        return self.bioport_biography.get_namen()
    
    def get_non_bioport_namen(self):
        namen = self.merged_biography.get_names()
        namen = [naam for naam in namen if naam.to_string() not in [n.to_string() for n in self.get_bioport_namen()]]
        return namen
    
    def get_namen(self):
        namen = self.merged_biography.get_names()
        return namen
    
    def get_value(self, k, biography=None):
        if not biography:
            biography = self.merged_biography
        if k in ['geboortedatum', 'sterfdatum']:
            return to_ymd(biography.get_value(k, ''))
        else:
            return biography.get_value(k, '')
        
    def status_value(self, event_id, attr):
        """return 'bioport' if the value is added by the editors of the biographical portal
        return 'merged' if the value comes from the merged_biography"""
        bioport_event = self.get_event(event_id, biography=self.bioport_biography)
        if bioport_event is None:
            bioport_event = self.get_state(event_id)
#        merged_event = self.get_event(self.merged_biography)
        if getattr(bioport_event, attr, None):
            return 'bioport'
        else:
            return 'merged'
        
        if self.bioport_biography.get_value(k):
            return 'bioport'
        elif self.merged_biography.get_value(k):
            return 'merged'
        else:
            return ''    
        
    def validate_event(self, action, data):
        pass
    def _get_date_from_request(self, prefix):
        y = self.request.get('%s_y' % prefix)
        m = self.request.get('%s_m' % prefix)
        d = self.request.get('%s_d' % prefix)
        ymd = from_ymd(y, m, d)
        return ymd or ''
    
    def _set_event(self, type):
        when = self._get_date_from_request('%s' % type )
        notBefore = self._get_date_from_request('%s_notBefore' % type)
        notAfter = self._get_date_from_request('%s_notAfter' % type)
        date_text = self.request.get('%s_text' % type)
        place = self.request.get('%s_place' % type)
        self.bioport_biography.add_or_update_event(type, when=when, date_text=date_text, notBefore=notBefore, notAfter=notAfter, place=place)
        
    def _save_state(self, type):
        frm = self._get_date_from_request(prefix='state_%s_from' % type)
        to = self._get_date_from_request(prefix='state_%s_to' % type)
        text = self.request.get('state_%s_text' % type)
        self.bioport_biography.add_or_update_state(type, frm=frm, to=to, text=text)
        
    @grok.action('bewaar beroep', name="save_occupation")
    def save_occupation(self):
        self._set_occupation()
        self.save_biography()
        self.msg = 'beroep bewaard' 
    
    
    def _set_occupation(self):
        occupation_ids = self.request.get('occupation_id', [])
        to_delete = []
        if type(occupation_ids) != type([]):
            occupation_ids = [occupation_ids]
        for idx in range(len(occupation_ids)):
            occupation_id = occupation_ids[idx] 
            if occupation_id:
                name = self.repository.get_occupation(occupation_id).name  
                self.bioport_biography.add_or_update_state(type='occupation', idno=occupation_id, text=name, idx=idx)
            else:
                to_delete.append(idx) 
                
        to_delete.reverse()
        for idx in to_delete:
            self.bioport_biography.remove_state(type='occupation', idx=idx)
            
        new_occupation_ids = self.request.get('new_occupation_id')
        if type(new_occupation_ids) != type([]):
            new_occupation_ids = [new_occupation_ids]
        new_occupation_ids = [s for s in new_occupation_ids if s ]
        for new_occupation_id in new_occupation_ids:
            name = self.repository.get_occupation(new_occupation_id).name 
            self.bioport_biography.add_state(type='occupation', idno=new_occupation_id, text=name)
    

    def save_biography(self):
        if not self.person.status:
            self.person.status = 2 #set status to bewerkt
        self.repository.save_person(self.person)
        self.repository.save_biography(self.bioport_biography)
        #we need to reload merged_biography because changes are not automatically picked up
        self.person.refresh()
        self.merged_biography  = self.person.get_merged_biography()

    @grok.action('bewaar geslacht', name="save_sex")
    def save_sex(self):
        self._set_sex()
        self.save_biography()
        self.msg = 'geslacht bewaard' 
        
    def _set_sex(self): 
        self.bioport_biography.set_value('geslacht', self.request.get('sex'))
        
    @grok.action('bewaar geboorte', name="save_event_birth", validator=validate_event)
    def save_event_birth(self):
        self._set_event('birth')
        self.save_biography()
        self.msg = 'geboortedatum bewaard'
        
           
    @grok.action('bewaar dood', name='save_event_death')
    def save_event_death(self):
        self._set_event('death')
        self.save_biography()
        self.msg = 'sterfdatum bewaard'
        
    @grok.action('bewaar doop', name='save_event_baptism')
    def save_event_baptism(self):
        self._set_event('baptism')
        self.save_biography()
        self.msg = 'doopdatum veranderd'
            
    @grok.action('bewaar begrafenis', name='save_event_funeral')
    def save_event_funeral(self):
        self._set_event('funeral')
        self.save_biography()
        self.msg = 'begraafdatum veranderd'
            
         
    @grok.action('verander naam', name='change_name')  
    def change_name(self):
        self.redirect(self.url(self.__parent__, 'changename', data={'bioport_id':self.bioport_id}))
    
    @grok.action('bewaar actief', name='save_state_floruit')
    def save_state_floruit(self): 
        self._save_state('floruit')
        self.save_biography()
        self.msg = 'actief veranderd'
        
    @grok.action('bewaar status', name='save_status')
    def save_status(self): 
        self._set_status()
        self.msg = 'status veranderd'
        self.save_biography()
    
    def _set_status(self):
        status = self.request.get('status')
        if status: 
            status = int(status)
        self.person.status = status 
    

        
    @grok.action('bewaar opmerkingen', name='save_remarks')
    def save_remarks(self): 
        self._save_remarks()
        self.msg = 'opmerkingen bewaard'
    
    def _save_remarks(self): 
        self.person.remarks = self.request.get('remarks')
        self.repository.save_person(self.person)
       
        
    @grok.action('bewaar alle veranderingen', name='save_everything')  
    def save_everything(self):
        self._set_event('birth')
        self._set_event('death')
        self._set_event('funeral')
        self._set_event('baptism')
        self._set_sex()
        self._set_occupation()
        self._save_state('floruit')
        self._set_status()
        self._save_remarks()
        self.save_biography()
        self.msg = 'alle ingevulde waardes bewaard'
        
    @grok.action('voeg toe', name='add_name') 
    def add_name(self):
        name = Naam(
#            repositie = self.request.get('prepositie'),
#            voornaam = self.request.get('voornaam'),
#            intrapositie = self.request.get('intrapositie'),
#            geslachtsnaam = self.request.get('geslachtsnaam'),
#            postpositie = self.request.get('postpositie'),
            volledige_naam = self.request.get('name_new'),
        )
        
        #add the namen van de "merged biographies" als we dat nog niet hebben gedaan
        if not self.bioport_biography.get_namen():
            for naam in self.merged_biography.get_names():
                self.bioport_biography._add_a_name(naam)
        
        self.bioport_biography._add_a_name(name)
        self.save_biography()
        self.msg = 'added a name'
    
    @grok.action('verwijder', name='remove_name')
    def remove_name(self):
        idx = self.request.get('naam_idx')
        idx = int(idx)
        if len(self.bioport_biography.get_namen()) == 1:
            self.msg = 'naam kon niet worden verwijderd: er is tenminste 1 naam nodig'
        else: 
            self.bioport_biography.remove_name(idx)
            self.save_biography()
            self.msg = 'naam verwijderd'
            
class PersoonIdentify(MostSimilar, Persons, Persoon):
    
    def update(self, **args):
        Persons.update(self, **args)
        MostSimilar.update(self, **args)
        #Persoon.update(self, **args)
#        self.persons =Batch([])
#        self.persons.grand_total = 0
        self.bioport_ids = self.request.get('bioport_ids', [])
        if type(self.bioport_ids) != type([]):
            self.bioport_ids = [self.bioport_ids]
        if self.request.get('new_bioport_id'):
            self.bioport_ids.append(self.request.get('new_bioport_id'))
        self.selected_persons = [self.context.repository().get_person(bioport_id) for bioport_id in self.bioport_ids]
        self.selected_persons = [p for p in self.selected_persons if p]

        self.persons = []
        


class IdentifyMoreInfo(MostSimilar, Persons, Persoon):
    def update(self, bioport_ids=[]):
        MostSimilar.update(self)
        repo = self.context.repository()
        persons = [BioPortRepository.person.Person(id, repository=repo) for id in bioport_ids]
        self.bioport_ids = bioport_ids
        self.persons = persons
        self.redirect_to = self.request.get('redirect_to') or self.request.get('HTTP_REFERER')
        if self.redirect_to:
            self.redirect_to = self.redirect_to.split('?')[0]
        

class ChangeName(Persoon, grok.EditForm): 
    
    def update(self, **args):
        Persoon.update(self, **args)
        self.bioport_id = self.request.get('bioport_id')         
        if not self.bioport_id:
            #XXX make a userfrienlider error
            assert 0, 'need bioport_id in the request'
        self.person  = self.context.get_person(bioport_id=self.bioport_id)  
        self.bioport_biography  = self.context.repository().get_bioport_biography(self.person)
        
        if not self.bioport_biography.get_namen():
            for naam in self.person.get_merged_biography().get_names():
                self.bioport_biography._add_a_name(naam)
            self.save_biography()
        
        self.idx = self.request.get('idx')         
        if not self.idx or self.idx == u'new':
            self.naam = None
        else:
            self.idx = int(self.idx) 
            self.naam  = self.bioport_biography.get_namen()[self.idx] 
       
    @grok.action('bewaar veranderingen', name='save_changes') 
    def save_changes(self):
        bio = self.bioport_biography
        
        parts = ['prepositie', 'voornaam', 'intrapositie', 'geslachtsnaam', 'postpositie']
        args = dict([(k, self.request.get(k)) for k in parts])
        
        volledige_naam = self.request.get('volledige_naam')
            
        #als de volledige naam niet is veranderd, maar een van de oude velden wel
        #dan, ja, dan wat?
        if volledige_naam in ' '.join(parts):
            volledige_naam = ' '.join(parts)
        
        name = Naam(
            volledige_naam = volledige_naam,
            **args
        )
        repository = self.context.repository()
        bio._replace_name(name, self.idx)
        repository.save_biography(bio)
        self.msg = 'changed a name'
        
    

    
    
class AntiIdentified(grok.View):
    pass

class Identified(grok.View):
    pass

class Deferred(grok.View):
    def update(self, **args):
        self.redirect_to = None
    
class Uitleg(grok.View): 
    pass
   
class Uitleg_Zoek(grok.View):        
    pass   
    
class Locations(grok.View):     
    def update(self, **kw):
        self.batch_start = int(self.request.get('batch_start', 0))
        self.batch_size = int(self.request.get('batch_size', 30))
        self.startswith = self.request.get('startswith', None)
        self.name = self.request.get('name', None)
        
    def get_locations(self):
        ls = self.context.repository().db.get_locations(startswith=self.startswith, name=self.name)
        
        batch = Batch(ls, start=self.batch_start, size=self.batch_size)
        batch.grand_total = len(ls)
        return batch
    
class ChangeLocation(Locations):    
    def update(self, **kw):
        Locations.update(self)
        self.location = self.request.get('place_id')

class Identify(grok.View):
    pass