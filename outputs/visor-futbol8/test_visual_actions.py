import copy,unittest,numpy as np
from contact_identity import resolve_contact
from goal_geometry import approach_proposals,GoalImageTracker
from sequence_engine import sequence_actions
from trajectory_identity import stabilize


def body(tid,pid=None,x=0):
    return {'id':tid,'kit':'orange','player_id':pid,'person_track_id':'c'+str(tid),'box':[x,0,x+40,100],'identity':{'state':'unknown' if pid is None else 'estimated'}}


class VisualActionsTests(unittest.TestCase):
    def fixture(self):
        actor=body(1);rs=[{'time':1,'tracks':[actor]},{'time':1.04,'tracks':[body(2,'orange-7',2)]},{'time':1.08,'tracks':[body(2,'orange-7',4)]}]
        return actor,rs,{'actor':actor,'last':rs[0]},[r['time'] for r in rs],{r['time']:np.zeros(2) for r in rs}
    def test_contact_name_survives_unique_body_handoff(self):
        a,rs,ep,ts,off=self.fixture();q=resolve_contact(ep,rs,ts,off);self.assertEqual(q['player_id'],'orange-7');self.assertIsNone(a['player_id'])
    def test_single_future_body_cannot_name_a_contact(self):
        a,rs,ep,ts,off=self.fixture();self.assertIsNone(resolve_contact(ep,rs[:2],ts[:2],off))
    def test_two_nearby_people_stop_contact_handoff(self):
        a,rs,ep,ts,off=self.fixture()
        for r in rs[1:]:r['tracks'].append(body(3,'orange-41',8))
        self.assertIsNone(resolve_contact(ep,rs,ts,off))
    def test_manual_unknown_contact_is_preserved(self):
        a,rs,ep,ts,off=self.fixture();a['identity']={'state':'rejected','method':'manual_review'};self.assertIsNone(resolve_contact(ep,rs,ts,off))
    def test_a_simultaneously_visible_known_body_is_not_the_contact(self):
        a,rs,ep,ts,off=self.fixture();rs[0]['tracks'].append(body(2,'orange-7',2));self.assertIsNone(resolve_contact(ep,rs,ts,off))
    def test_conflicting_adjacent_names_do_not_win_by_majority(self):
        a,rs,ep,ts,off=self.fixture();rs[2]['tracks'][0]['player_id']='orange-41';self.assertIsNone(resolve_contact(ep,rs,ts,off))
    def flight(self):
        return [{'time':i*.1,'mouth':[1.8-i*.15,.5],'measurement':'neural_detection'} for i in range(8)]
    def test_goal_approach_is_a_proposal_and_not_a_certified_goal(self):
        q=approach_proposals(self.flight(),0);self.assertEqual(len(q),1);self.assertFalse(q[0]['crossing_certified']);self.assertEqual(q[0]['class'],'Visual goal approach')
    def test_flight_away_from_goal_does_not_propose_a_shot(self):
        rs=self.flight();points=[r['mouth'] for r in rs][::-1]
        for r,p in zip(rs,points):r['mouth']=p
        self.assertEqual(approach_proposals(rs,0),[])
    def test_components_without_neural_support_cannot_propose_shot(self):
        rs=self.flight()
        for r in rs:r['measurement']='compact_image_component'
        self.assertEqual(approach_proposals(rs,0),[])
    def test_visual_proposal_does_not_become_a_goal_or_automatic_statistic(self):
        event=approach_proposals(self.flight(),0)[0];events,_=sequence_actions([], [event],True)
        self.assertEqual(events[0]['kind'],'shot');self.assertEqual(events[0]['state'],'candidate');self.assertIsNone(events[0]['player_id'])
    def test_native_intermediate_box_keeps_unique_physical_identity(self):
        rs=[{'time':i*.1,'frame':i,'tracks':[body(tid,pid,x)],'ball':None} for i,(tid,pid,x) in enumerate([(1,'orange-41',0),('N3-1',None,2),(1,'orange-41',4)])]
        # Accepted identity evidence must have an anchor, as in real source records.
        for r in (rs[0],rs[2]):r['tracks'][0]['identity']['method']='jersey_vote'
        cs,_=stabilize(rs);self.assertEqual(len(cs),1);self.assertEqual([r['tracks'][0]['player_id'] for r in rs],['orange-41']*3)
class DerivedContactReviewTests(unittest.TestCase):
    def check(self,decision,new_pid=None):
        import tempfile,json,shutil
        from pathlib import Path
        from server import App,ROOT
        from analytics_v3 import profiles_for
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'data').mkdir();(root/'automatic/chunks').mkdir(parents=True);shutil.copy2(ROOT/'plantilla.json',root/'plantilla.json')
            def write(name,value):(root/(name+'.json')).write_text(json.dumps(value),encoding='utf8')
            rs=[{'time':1,'frame':30,'tracks':[body(1)],'ball':None},{'time':1.04,'frame':31,'tracks':[body(2,'orange-7',2)],'ball':None},{'time':1.08,'frame':32,'tracks':[body(2,'orange-7',4)],'ball':None}]
            actor={'player_id':'orange-7','support':[{'time':1.04,'track_id':2,'context_id':'c2'},{'time':1.08,'track_id':2,'context_id':'c2'}]}
            events=[{'id':'e','kind':'pass','time':1,'source_track':1,'target_track':3,'player_id':'orange-7','receiver_id':'orange-41','team':'orange','state':'estimated','outcome':'complete','sequence':{'source_contact_identity':actor}}]
            write('data/metadata',{'duration':10});write('automatic/review-manifest',{'source_key':'fixture'});write('automatic/quality',{'version':7});write('automatic/chunks/000',rs);write('automatic/actions',events);write('automatic/lineup',{});write('automatic/identity-segments',[]);write('automatic/memory-quality',{});write('automatic/profiles',profiles_for(rs,events,json.loads((root/'plantilla.json').read_text(encoding='utf8'))['players'],10))
            write('automatic/uncertainties',[{'id':'i','category':'identity','track_id':2,'context_id':'c2','start':1.04,'end':1.08,'time':1.04,'player_id':'orange-7'}])
            app=App(root);value={'source_key':'fixture','decision':decision}
            if new_pid:value['data']={'player_id':new_pid}
            app.review_engine.save('i',value);out=app.review_engine.effective();return out['actions'][0],out['team_passes']
    def test_rejecting_adjacent_reference_removes_derived_contact_name(self):
        event,passes=self.check('rejected');self.assertIsNone(event['player_id']);self.assertEqual(passes['unattributed'],1)
    def test_correcting_adjacent_reference_updates_derived_contact_name(self):
        event,passes=self.check('corrected','orange-22');self.assertEqual(event['player_id'],'orange-22');self.assertEqual(passes['attributed'],1)
    def test_identity_review_cannot_count_a_pass_to_itself(self):
        event,passes=self.check('corrected','orange-41');self.assertEqual(event['state'],'candidate');self.assertEqual(passes['detected'],0)

if __name__=='__main__':unittest.main()
