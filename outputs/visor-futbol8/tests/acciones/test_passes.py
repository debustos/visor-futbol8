"""Pass regressions for intermittent identity, unavailable geometry and false boots."""
import copy,unittest,tempfile,json,shutil
from pathlib import Path
from f8.plataforma.server import App,ROOT
from f8.publicacion.analytics_v3 import profiles_for
import numpy as np
from f8.acciones.contactos import infer_possession;from f8.balon.seleccion import select_ball
from f8.acciones.sequence_engine import sequence_actions
from f8.acciones.pass_engine import contact_episodes,pass_summary
from f8.balon.ball_continuity import refine
from f8.plataforma.season_store import aggregate_parts

class PassTests(unittest.TestCase):
    def sequence(self):
        rows=[]
        for i in range(5):
            a={'id':1,'segment_id':'a','player_id':'orange-41','kit':'orange','box':[80,30,120,100],'position':None}
            b={'id':2,'segment_id':'b','player_id':'orange-7','kit':'orange','box':[180,30,220,100],'position':None}
            x=100 if i<2 else 150 if i==2 else 200
            r={'time':i*.1,'tracks':[a,b],'ball':{'center':[x,100],'confidence':.9,'position':None},'possession':{'track_id':1 if i<2 else 2,'distance':.1} if i!=2 else None};rows.append(r)
        return rows
    def test_free_flight_chooses_measured_continuation_over_confident_boot_jump(self):
        rs=[]
        for i in range(3):
            ball={'box':[10+i*10,100,20+i*10,110],'center':[15+i*10,105],'confidence':.8,'position':None}
            rs.append({'time':i*.1,'tracks':[],'ball':ball})
        rs[-1]['ball']={'box':[250,100,260,110],'center':[255,105],'confidence':.95,'position':None}
        rs[-1]['ball_candidates']=[{'box':[30,100,40,110],'confidence':.65}]
        q=refine(rs);self.assertEqual(rs[-1]['ball']['center'],[35,105]);self.assertEqual(q['reselected_measured_candidates'],1)
    def test_missing_free_flight_detection_is_never_created(self):
        rs=[{'time':i*.1,'tracks':[],'ball':{'box':[i*10,100,i*10+10,110],'center':[i*10+5,105],'confidence':.8,'position':None}} for i in range(2)]
        rs.append({'time':.2,'tracks':[],'ball':None});refine(rs);self.assertIsNone(rs[-1]['ball'])
    def test_unique_unassigned_detection_keeps_physical_contact_identity(self):
        rs=self.sequence();rs[1]['tracks'][0]['id']='D100-0';rs[1]['tracks'][0]['player_id']=None;rs[1]['tracks'][0]['segment_id']=None;rs[1]['possession']['track_id']='D100-0'
        es,_=sequence_actions(rs,[],True);self.assertEqual(es[0]['player_id'],'orange-41');self.assertEqual(es[0]['state'],'estimated');self.assertEqual(es[0]['sequence']['source_physical_alias_links'],1)
    def test_two_visible_people_are_never_merged_as_an_alias(self):
        rs=self.sequence();other=copy.deepcopy(rs[1]['tracks'][0]);other['id']='D100-0';other['player_id']=None;rs[1]['tracks'].append(other);rs[1]['possession']['track_id']='D100-0'
        eps=contact_episodes(rs,True);self.assertTrue(all(e['aliases']==0 for e in eps))
    def test_pass_without_pitch_projection(self):
        es,_=sequence_actions(self.sequence(),[],short_contacts=True);self.assertEqual([(e['kind'],e['state']) for e in es],[('pass','estimated')])
    def test_no_jersey_at_last_contact_keeps_same_physical_actor(self):
        rs=self.sequence();rs[1]['tracks'][0]['player_id']=None
        es,_=sequence_actions(rs,[],short_contacts=True);self.assertEqual(es[0]['player_id'],'orange-41');self.assertEqual(es[0]['state'],'estimated')
        self.assertEqual(len(contact_episodes(rs,True)),2)
    def test_conflicting_identity_in_contact_is_unattributed(self):
        rs=self.sequence();rs[1]['tracks'][0]['player_id']='orange-22';es,_=sequence_actions(rs,[],short_contacts=True)
        self.assertIsNone(es[0]['player_id']);self.assertEqual(pass_summary(es)['unattributed'],1)
    def test_anonymous_passer_is_kept_without_inventing_name(self):
        rs=self.sequence()
        for r in rs:r['tracks'][0]['player_id']=None
        es,_=sequence_actions(rs,[],short_contacts=True);self.assertEqual(pass_summary(es)['detected'],1);self.assertEqual(pass_summary(es)['attributed'],0)
    def test_extended_foot_is_contact_without_calibration(self):
        r={'ball':{'center':[68,99]},'tracks':[{'id':1,'kit':'orange','position':None,'box':[80,30,120,100]}]}
        self.assertEqual(infer_possession(r)['track_id'],1)
    def test_ball_at_chest_is_not_foot_contact(self):
        r={'ball':{'center':[100,55]},'tracks':[{'id':1,'kit':'orange','position':None,'box':[80,30,120,100]}]};self.assertIsNone(infer_possession(r))
    def test_image_ball_survives_missing_homography(self):
        im=np.full((120,120,3),(60,130,70),np.uint8);b=select_ball([{'box':[15,45,25,55],'confidence':.9}],0,None,None,im)
        self.assertEqual(b['center'],[20,50]);self.assertIsNone(b['position'])
    def test_boot_hopping_between_feet_without_free_flight_is_candidate(self):
        rs=self.sequence();rs[2]['possession']={'track_id':1,'distance':.1};es,_=sequence_actions(rs,[],short_contacts=True)
        self.assertTrue(es);self.assertTrue(all(e['state']=='candidate' for e in es))
    def test_team_totals_and_unknown_actions_survive_round_aggregation(self):
        rs=self.sequence()
        for r in rs:r['tracks'][0]['player_id']=None
        es,_=sequence_actions(rs,[],short_contacts=True)
        parts=[{'round':2,'half':1,'duration':10,'state':'complete','attack_direction':'up'}]
        result=aggregate_parts([],parts,{(2,1):{'actions':es,'profiles':[]}}, {'kind':'round'})
        self.assertEqual(result['team_passes']['detected'],1);self.assertEqual(result['unattributed_passes'][0]['half'],1)
    def test_rival_only_transfer_never_produces_own_team_pass(self):
        rs=self.sequence()
        for r in rs:
            for b in r['tracks']:b['kit']='opponent';b['player_id']=None
        es,_=sequence_actions(rs,[],short_contacts=True);self.assertFalse(any(e['kind']=='pass' for e in es))
class PassReviewTests(unittest.TestCase):
    def test_geometry_review_does_not_erase_episode_identity_or_anonymous_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'data').mkdir();(root/'automatic/chunks').mkdir(parents=True)
            shutil.copyfile(ROOT/'plantilla.json',root/'plantilla.json')
            def write(name,value):(root/(name+'.json')).write_text(json.dumps(value),encoding='utf8')
            write('data/metadata',{'duration':10});write('automatic/review-manifest',{'source_key':'fixture'});write('automatic/quality',{})
            records=[{'time':1,'tracks':[{'id':1,'kit':'orange','player_id':None,'position':None}]}]
            events=[{'id':'known','kind':'pass','time':1,'source_track':1,'player_id':'orange-41','receiver_id':'orange-7','state':'estimated','outcome':'complete'},{'id':'unknown','kind':'pass','time':2,'source_track':2,'player_id':None,'receiver_id':'orange-7','state':'estimated','outcome':'complete'}]
            write('automatic/chunks/000',records);write('automatic/actions',events);write('automatic/lineup',{})
            roster=json.loads((root/'plantilla.json').read_text())['players'];write('automatic/profiles',profiles_for(records,events,roster,10));write('automatic/uncertainties',[{'id':'geometry','category':'geometry','time':1,'start':0,'end':3}])
            app=App(root);app.review_engine.save('geometry',{'source_key':'fixture','decision':'confirmed','data':{'state':'accepted'}})
            out=app.review_engine.effective();self.assertEqual(out['team_passes']['detected'],2);self.assertEqual(out['team_passes']['unattributed'],1);self.assertEqual(out['actions'][0]['player_id'],'orange-41')
if __name__=='__main__':unittest.main()
