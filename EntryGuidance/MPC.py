""" 
Model Predictive Controllers

    Standard NMPC - use a prediction model to optimize a bank profile over a receding horizon
    Joel's NMPC - use the taylor expansion of the current state to predict a future state, and determines the optimal control over the interval
    Robust NMPC - adds a feedback control element to the nominal solution generated by an open-loop NMPC
    
"""

# Elements: 
#   Optimization:
#       propagation of prediction model for a given control sequence -  controller needs to be passed a system model and initial state
#       computation of some cost function (generally difference between predicted states and reference states) - controller needs reference data in some format, or possibly just pass a cost function that takes standard arguments
#       iteration to improve control sequence until convergence - need a reliable optimization routine (although with smaller parametrizations, brute force could even be used)

from scipy.integrate import odeint, trapz
from scipy.optimize import minimize, differential_evolution, minimize_scalar
from functools import partial
from numpy import pi
import numpy as np

def constant(value, **kwargs):
    return value

def options(N,T):
    """ Defines the parameters used in NMPC """
    opt = {}
    
    opt['N'] = N            # Integer number of time steps to predict forward, also the number of control segments
    opt['T'] = T            # Total prediction length
    
    opt['dt'] = float(T)/N  # Length of each step in the prediction
    
    return opt


def controller(control_options, control_bounds, references, **kwargs):

    bounds = [control_bounds]*control_options['N']    
    
    sol = optimize(kwargs['current_state'], control_options, bounds, kwargs['aero_ratios'], references)
    
    vf = lateral(kwargs['velocity'], kwargs['drag'],kwargs['fpa'],control_options['T'])
    if control_options['N'] > 1:
        return sol.x[0]*np.sign(references['bank'](vf))
    else:
        return sol.x*np.sign(references['bank'](vf))

def lateral(velocity,drag,fpa,T):
    vdot = drag*np.sin(fpa)-3.7
    vf = velocity + T*vdot
    return vf
        
def optimize(current_state, control_options, control_bounds, aero_ratios, reference):
    from Simulation import Simulation, NMPCSim
    
    
    sim = Simulation(output=False, **NMPCSim(control_options))

    guess = [pi/6]*control_options['N']
    if control_options['N'] > 1:
        scalar = False
        # sol = minimize(cost, guess, args=(sim, current_state, aero_ratios, reference), 
                       # method='L-BFGS-B', bounds=control_bounds, tol=1e-2, options={'disp':False}) # Seems to work okay!
        sol = minimize(cost, guess, args=(sim, current_state, aero_ratios, reference, scalar), 
                       method='SLSQP', bounds=control_bounds, tol=1e-4, options={'disp':False}) # Seems to work okay!               
    # sol = differential_evolution(cost, args=(sim, x0), bounds=bounds, tol=1e-1, disp=True)
    else:
        scalar = True
        sol = minimize_scalar(cost, method='Bounded', bounds=control_bounds[0], args=(sim, current_state, aero_ratios, reference, scalar))
    
    return sol
    
def cost(u, sim, state, ratios, reference, scalar):
    if scalar:
        controls = [partial(constant,value=u)]
    else:
        controls = [partial(constant, value=v) for v in u]
    output = sim.run(state, controls, AeroRatios=ratios)
    time = output[:,0]
    drag = output[:,13]
    vel = output[:,7]
    range = output[:,10]
    fpa = np.radians(output[:,8])
    # lift = output[:,12]
    
    if 1:                                   # Pure drag tracking
        drag_ref = reference['drag'](vel)
        integrand = 1*(drag-drag_ref)**2
    else:
        drag_ref = reference['dragcos'](vel) # Tracking D/cos(fpa) - which is the true integrand in energy integral
        integrand = 1*(drag/np.cos(fpa)-drag_ref)**2
    
    # rtg_ref = reference['range'](vel)/1000
    
    return trapz(integrand, time)
    
    
def testNMPC():
    from Simulation import Simulation, Cycle, EntrySim, SRP
    import matplotlib.pyplot as plt
    from ParametrizedPlanner import HEPBank
    # from JBG import controller as srp_control
    from Triggers import AccelerationTrigger, VelocityTrigger, RangeToGoTrigger
    from Uncertainty import getUncertainty
    
    # Plan the nominal profile:
    reference_sim = Simulation(cycle=Cycle(1),output=False,**EntrySim())
    bankProfile = lambda **d: HEPBank(d['time'],*[ 165.4159422 ,  308.86420218,  399.53393904])
    
    r0, theta0, phi0, v0, gamma0, psi0,s0 = (3540.0e3, np.radians(-90.07), np.radians(-43.90),
                                             5505.0,   np.radians(-14.15), np.radians(4.99),   1000e3)
                                             
    x0 = np.array([r0, theta0, phi0, v0, gamma0, psi0, s0, 8500.0])
    output = reference_sim.run(x0,[bankProfile])

    references = reference_sim.getRef()
    drag_ref = references['drag']
    
    
    # Create the simulation model:
        
    states = ['PreEntry','Entry']
    # conditions = [AccelerationTrigger('drag',4), VelocityTrigger(500)]
    conditions = [AccelerationTrigger('drag',4), RangeToGoTrigger(0)]
    input = { 'states' : states,
              'conditions' : conditions }
              
    sim = Simulation(cycle=Cycle(1),output=True,**input)

    # Create the controllers
    
    option_dict = options(N=1,T=5)
    mpc = partial(controller, control_options=option_dict, control_bounds=(0,pi/2), references=references)
    pre = partial(constant, value=bankProfile(time=0))
    controls = [pre,mpc]
    
    # Run the off-nominal simulation
    perturb = getUncertainty()['parametric']
    sample = None 
    # sample = perturb.sample()
    # sample = [ 0.0319597,   -0.01117027,  0.0, 0.0]
    x0_nav = [r0, theta0, phi0, v0, gamma0, psi0, s0, 8500.0] # Errors in velocity and mass
    x0_full = np.array([r0, theta0, phi0, v0, gamma0, psi0, s0, 8500.0] + x0_nav + [1,1] + [np.radians(-15),0])

    if 1:
        output = sim.run(x0, controls, sample, FullEDL=False)
        reference_sim.plot()
        
    else:
        output = sim.run(x0_full, controls, sample, FullEDL=True)
    
    Dref = drag_ref(output[:,7])
    D = output[:,13]
    Derr = D-Dref
    DerrPer = 100*Derr/Dref
    Ddotref = np.diff(Dref)/np.diff(output[:,0])
    Dddotref = np.diff(Dref,n=2)/np.diff(output[1:,0])
   
    plt.figure(666)
    plt.plot(output[:,7],DerrPer)
    plt.ylabel('Drag Error (%)')
    plt.xlabel('Velocity (m/s)')
    
    sim.plot()
    sim.show()
    
    
if __name__ == '__main__':
    testNMPC()