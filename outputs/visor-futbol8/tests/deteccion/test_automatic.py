"""Regression tests for dangerous false-identity and false-event interpretations."""
import unittest,numpy as np
from f8.identidad.dorsales import jersey_vote;from f8.balon.seleccion import select_ball;from f8.acciones.contactos import action_candidates;from f8.publicacion.alineacion_basica import infer_changes
from f8.acciones.automatic_fusion import substitutions
from f8.deteccion.analyze_automatic import identify
from f8.acciones.ball_actions import trajectory_actions

class AutomaticTests(unittest.TestCase):
    def test_correlated_crops_are_not_independent_identity_evidence(self):
        readings=[{'text':'41','score':.99,'frame':7} for i in range(6)]
        self.assertIsNone(jersey_vote(readings,{41,14})[0])
    def test_weak_repeated_wrong_number_does_not_create_a_player(self):
        readings=[{'text':'14','score':.85,'frame':i} for i in range(5)]
        self.assertIsNone(jersey_vote(readings,{41,14})[0])
    def test_competing_dorsals_force_abstention(self):
        readings=[{'text':str(n),'score':.97,'frame':i} for i,n in enumerate([41,14,41,14])]
        self.assertIsNone(jersey_vote(readings,{41,14})[0])
    def test_true_independent_anchor(self):
        readings=[{'text':'41','score':.85,'localized':True,'frame':i} for i in (10,20,30)]
        self.assertEqual(jersey_vote(readings,{41})[0],41)
    def test_partial_99_cannot_become_9_from_repeated_clipped_crops(self):
        readings=[{'text':'9','score':.99,'localized':True,'frame':i} for i in (1,2,3)]
        readings.append({'text':'99','score':.32,'localized':True,'frame':4})
        self.assertIsNone(jersey_vote(readings,{9,99})[0])
    def test_full_number_wins_over_clipped_number_in_the_same_frame(self):
        readings=[r for i in (1,2,3) for r in ({'text':'9','score':.99,'frame':i},{'text':'99','score':.85,'localized':True,'frame':i})]
        self.assertEqual(jersey_vote(readings,{9,99})[0],99)
    def test_simultaneous_equal_jersey_claims_do_not_select_an_arbitrary_player(self):
        features=np.eye(2,dtype=np.float32);summaries=[{'id':i,'embedding_rows':[i-1],'kit_counts':{'orange':4}} for i in (1,2)]
        records=[{'time':0,'tracks':[{'id':i,'kit':'orange'} for i in (1,2)]}];labels={i:{'number':41,'evidence':{'state':'accepted'}} for i in (1,2)}
        result=identify(records,summaries,[],features,labels,{41:{}})
        self.assertEqual(result[-1],2);self.assertTrue(all(b['player_id'] is None for b in records[0]['tracks']))
    def test_ambiguous_ball_is_not_ownership(self):
        img=np.full((120,120,3),(60,130,70),np.uint8);balls=[{'box':[15,45,25,55],'confidence':.5},{'box':[45,45,55,55],'confidence':.49}]
        self.assertIsNone(select_ball(balls,0,None,np.eye(3),img))
    def test_long_control_run_still_detects_later_pass_once(self):
        records=[]
        for i in range(40):
            tid=1 if i<32 else 2;pid='orange-41' if tid==1 else 'orange-7';p=[25 if tid==1 else 40,50]
            records.append({'time':i*.2,'possession':{'track_id':tid,'kit':'orange'},'ball':{'confidence':.8},'tracks':[{'id':tid,'player_id':pid,'kit':'orange','position':p}]})
        events=action_candidates(records);self.assertEqual(len(events),1);self.assertEqual(events[0]['kind'],'pass');self.assertEqual(events[0]['player_id'],'orange-41')
    def test_pass_to_own_box_is_not_attacking_ball_into_box(self):
        records=[]
        for i in range(8):
            tid=1 if i<4 else 2;pid='orange-41' if tid==1 else 'orange-1';p=[50,70 if tid==1 else 90]
            records.append({'time':i*.2,'possession':{'track_id':tid,'kit':'orange' if tid==1 else 'keeper'},'ball':{'confidence':.8},'tracks':[{'id':tid,'player_id':pid,'kit':'orange' if tid==1 else 'keeper','position':p}]})
        self.assertEqual([e['kind'] for e in action_candidates(records)],['pass'])
    def test_disappearance_is_never_a_substitution(self):
        records=[{'time':i*.2,'tracks':[{'id':1,'player_id':'orange-41','position':[50,50]}]} for i in range(6)]
        records.append({'time':100,'tracks':[{'id':2,'player_id':'orange-7','position':[50,50]}]})
        self.assertEqual(substitutions(records),[]);self.assertEqual(infer_changes({},records)['substitutions'],[])
    def test_lineup_does_not_fill_unseen_players(self):
        records=[{'time':i*.2,'tracks':[{'id':1,'player_id':'orange-41','position':[50,50]}]} for i in range(8)]
        result=infer_changes({},records);self.assertEqual(result['unidentified_slots'],7);self.assertEqual(result['state'],'incomplete')
    def test_short_touch_requires_a_measured_moving_ball_path(self):
        records=[]
        for i in range(6):
            owner=1 if i==0 else 2 if i==5 else None;pid='orange-41' if owner==1 else 'orange-7';p=[10+i*3,50]
            records.append({'time':i*.2,'possession':{'track_id':owner,'distance':.1} if owner else None,'ball':{'confidence':.9,'position':p},'tracks':[{'id':owner,'kit':'orange','player_id':pid,'position':p}] if owner else []})
        result=trajectory_actions(records);self.assertEqual(len(result),1);self.assertEqual(result[0]['kind'],'pass')
        for r in records:r['ball']['position']=[10,50]
        self.assertEqual(trajectory_actions(records),[])
    def test_missing_intermediate_ball_frames_do_not_become_an_automatic_pass(self):
        records=[]
        for i in range(6):
            owner=1 if i==0 else 2 if i==5 else None;p=[10+i*3,50]
            records.append({'time':i*.2,'possession':{'track_id':owner,'distance':.1} if owner else None,'ball':{'confidence':.9,'position':p} if owner else None,'tracks':[{'id':owner,'kit':'orange','player_id':f'orange-{owner}','position':p}] if owner else []})
        self.assertEqual(trajectory_actions(records),[])
if __name__=='__main__':unittest.main()
