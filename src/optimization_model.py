import pyomo.environ as po
try:
    import linear_constraints as lc
    from network.entities import Bus, Component
    from network.entities import components as cp
except:
    from . import constraints as lc
    from .network.entities import Bus, Component
    from .network.entities import components as cp


class OptimizationModel(po.ConcreteModel):
    """Create Pyomo model of the energy system.

    Parameters
    ----------
    entities : list with all entity objects
    timesteps : list with all timesteps as integer values
    options : nested dictionary with options to set. possible options are:
      invest, slack

    Returns
    -------
    m : pyomo.ConcreteModel

    """

    # TODO Cord: Take "next(iter(self.dict.values()))" where the first value of
    #            dict has to be selected
    def __init__(self, entities, timesteps, options=None):

        super().__init__()

        self.entities = entities
        self.timesteps = timesteps

        # get options
        self.invest = options.get("invest", False)
        self.slack = options.get("slack", {"excess": True,
                                           "shortage": False})

        # calculate all edges ([('coal', 'pp_coal'),...])
        self.all_edges = self.edges([e for e in self.entities
                                     if isinstance(e, Component)])

        lc.generic_variables(model=self, edges=self.all_edges,
                             timesteps=self.timesteps)

        # list with all necessary classes
        component_classes = (cp.Transformer.__subclasses__() +
                             cp.Sink.__subclasses__() +
                             cp.Source.__subclasses__() +
                             cp.Transport.__subclasses__())
        # set attributes lists per class with objects and uids for opt model
        for cls in component_classes:
            objs = [e for e in self.entities if isinstance(e, cls)]
            uids = [e.uid for e in objs]
            setattr(self, cls.lower_name + "_objs", objs)
            setattr(self, cls.lower_name + "_uids", uids)
            # "call" methods to add the constraints opt. problem
            if objs:
                getattr(self, cls.lower_name + "_model")(objs=objs, uids=uids)

        self.bus_model()
        self.objective()

    def bus_model(self):
        """bus model creates bus balance for all buses using pyomo.Constraint

        The bus model creates all full balance around all buses using
        the `linear_constraints.generic_bus_constraint()` function.
        Additionally it sets constraints to model limits over the timehorizon
        for resource buses using `linear_constraints.generic_limit()

        Parameters
        ----------
        self : pyomo.ConcreteModel

        Returns
        -------
        self : pyomo.ConcreteModel
        """
        # get all bus objects
        self.bus_objs = [e for e in self.entities if isinstance(e, Bus)]
        # get uids from bus objects
        self.bus_uids = [e.uid for e in self.bus_objs]

        # slack variables that assures a feasible problem
        if self.slack["excess"] is True:
            self.excess_slack = po.Var(self.bus_uids, self.timesteps,
                                       within=po.NonNegativeReals)
        if self.slack["shortage"] is True:
            self.shortage_slack = po.Var(self.bus_uids, self.timesteps,
                                         within=po.NonNegativeReals)

        # select only "energy"-bus objects for bus balance constraint
        energy_bus_objs = [obj for obj in self.bus_objs
                           if any([obj.type == "el", obj.type == "th"])]
        energy_bus_uids = [obj.uid for obj in energy_bus_objs]

        # bus balance constraint for energy bus objects
        lc.generic_bus_constraint(self, objs=energy_bus_objs,
                                  uids=energy_bus_uids,
                                  timesteps=self.timesteps)

        # select only buses that are resources (gas, oil, etc.)
        resource_bus_objs = [obj for obj in self.bus_objs
                             if all([obj.type != "el", obj.type != "th"])]
        resource_bus_uids = [e.uid for e in resource_bus_objs]

        # set limits for resource buses
        lc.generic_limit(model=self, objs=resource_bus_objs,
                         uids=resource_bus_uids, timesteps=self.timesteps)

    def simple_transformer_model(self, objs, uids):
        """Generic transformer model containing the constraints
        for generic transformer components.

        Parameters
        ----------
        self : pyomo.ConcreteModel

        Returns
        -------
        self : pyomo.ConcreteModel
        """

        lc.generic_io_constraints(model=self, objs=objs, uids=uids,
                                  timesteps=self.timesteps)

        # set bounds for variables  models
        if self.invest is False:
            lc.generic_w_ub(model=self, objs=objs, uids=uids,
                            timesteps=self.timesteps)
        else:
            lc.generic_w_ub_invest(model=self, objs=objs, uids=uids,
                                   timesteps=self.timesteps)

    def simple_chp_model(self, objs, uids):
        """Simple combined heat and power model containing the constraints
        for simple chp components.

        Parameters
        ----------
        self : pyomo.ConcreteModel

        Returns
        -------
        self : pyomo.ConcreteModel

        """
        # use generic_transformer model for in-out relation and
        # upper / lower bounds
        self.simple_transformer_model(objs=objs, uids=uids)

        # use generic constraint to model PQ relation (P/eta_el = Q/eta_th)
        lc.generic_chp_constraint(model=self, objs=objs, uids=uids,
                                  timesteps=self.timesteps)

    def fixed_source_model(self, objs, uids):
        """fixed source model containing the constraints for
        fixed sources.

        Parameters
        ----------
        self : pyomo.ConcreteModel

        Returns
        -------
        self : pyomo.ConcreteModel
        """
        if self.invest is False:
            lc.generic_fixed_source(model=self, objs=objs, uids=uids,
                                    timesteps=self.timesteps)
        else:
            lc.generic_fixed_source_invest(model=self, objs=objs, uids=uids,
                                           timesteps=self.timesteps)

    def dispatch_source_model(self, objs, uids):
        """
        """
        if self.invest is False:
            lc.generic_dispatch_source(model=self, objs=objs, uids=uids,
                                       timesteps=self.timesteps)

    def simple_sink_model(self, objs, uids):
        """simple sink model containing the constraints for simple sinks
        Parameters
        ----------
        self : pyomo.ConcreteModel

        Returns
        -------
        self : pyomo.ConcreteModel
        """
        lc.generic_fixed_sink(model=self, objs=objs, uids=uids,
                              timesteps=self.timesteps)

    def simple_storage_model(self, objs, uids):
        """Simple storage model containing the constraints for simple storage
        components.

        Parameters
        ----------
        self : pyomo.ConcreteModel

        Returns
        -------
        self : pyomo.ConcreteModel
        """

        # set bounds for basic/investment models
        if(self.invest is False):
            lc.generic_w_ub(model=self, objs=objs, uids=uids,
                            timesteps=self.timesteps)
        else:
            gc.generic_soc_ub_invest(model=self, objs=objs, uids=uids,
                                     timesteps=self.timesteps)

            # constraint that limits discharge power by using the c-rate
            c_rate_out = {obj.uid: obj.c_rate_out
                          for obj in self.simple_storage_objs}
            out_max = {obj.uid: obj.out_max for obj in objs}
            O = {obj.uid: [o.uid for o in obj.outputs[:]] for obj in objs}

            def storage_discharge_limit_rule(self, e, t):
                expr = 0
                expr += self.w[e, O[e][0], t]
                expr += -(out_max[e][O[e][0]] + self.add_cap[e, O[e][0]]) \
                    * c_rate_out[e]
                return(expr <= 0)
            setattr(self, "simple_storage_w_ub_discharge_invest" +
                    objs[0].lower_name,
                    po.Constraint(uids, self.timesteps,
                                  rule=storage_discharge_limit_rule))

            # constraint that limits charging power by using the c-rate
            c_rate_in = {obj.uid: obj.c_rate_in
                         for obj in self.simple_storage_objs}
            in_max = {obj.uid: obj.in_max for obj in objs}
            I = {obj.uid: [i.uid for i in obj.inputs[:]] for obj in objs}

            def storage_charge_limit_rule(self, e, t):
                expr = 0
                expr += self.w[e, I[e][0], t]
                expr += -(in_max[e][I[e][0]] + self.add_cap[e, I[e][0]]) \
                    * c_rate_in[e]
                return(expr <= 0)
            setattr(self, "simple_storage_w_ub_charge_invest" +
                    objs[0].lower_name,
                    po.Constraint(uids, self.timesteps,
                                  rule=storage_charge_limit_rule))

        # constraint for storage energy balance
        O = {obj.uid: obj.outputs[0].uid for obj in objs}
        I = {obj.uid: obj.inputs[0].uid for obj in objs}
        soc_initial = {obj.uid: obj.soc_initial
                       for obj in self.simple_storage_objs}
        cap_loss = {obj.uid: obj.cap_loss for obj in self.simple_storage_objs}
        eta_in = {obj.uid: obj.eta_in[0] for obj in self.simple_storage_objs}
        eta_out = {obj.uid: obj.eta_out[0] for obj in self.simple_storage_objs}

        def storage_balance_rule(self, e, t):
            # TODO:
            #   - include time increment
            if(t == 0):
                expr = 0
                expr += self.soc[e, t] + soc_initial[e]
                expr += - self.soc[e, t+len(self.timesteps)-1]
                expr += - self.w[I[e], e, t] * eta_in[e]
                expr += + self.w[e, O[e], t] / eta_out[e]
                return(expr, 0)
            else:
                expr = self.soc[e, t] * (1 - cap_loss[e])
                expr += - self.soc[e, t-1]
                expr += - self.w[I[e], e, t] * eta_in[e]
                expr += + self.w[e, O[e], t] / eta_out[e]
                return(expr, 0)
        self.simple_storage_c = po.Constraint(uids, self.timesteps,
                                              rule=storage_balance_rule)

    def simple_transport_model(self, objs, uids):
        """Simple transport model building the constraints
        for simple transport components

        Parameters
        ----------
        m : pyomo.ConcreteModel

        Returns
        -------
        m : pyomo.ConcreteModel
        """

        self.simple_transformer_model(objs=objs, uids=uids)

    def objective(self):
        """Function that creates the objective function of the optimization
        model.

        Parameters
        ----------
        m : pyomo.ConcreteModel

        Returns
        -------
        m : pyomo.ConcreteModel
        """

        # create a combine list of all cost-related components
        cost_objs = (
            self.simple_chp_objs +
            self.simple_transformer_objs +
            self.simple_storage_objs +
            self.simple_transport_objs)

        self.cost_uids = {obj.uid for obj in cost_objs}

        I = {obj.uid: obj.inputs[0].uid for obj in cost_objs}
#        print("I: " + str(I))

        # create a combined list of all revenue related components
        revenue_objs = (
            self.simple_chp_objs +
            self.simple_transformer_objs)

        self.revenue_uids = {obj.uid for obj in revenue_objs}

        O = {obj.uid: obj.outputs[0].uid for obj in revenue_objs}

        # operational costs
        self.opex_var = {obj.uid: obj.opex_var for obj in cost_objs}
        self.input_costs = {obj.uid: obj.inputs[0].price
                            for obj in cost_objs}
        self.opex_fix = {obj.uid: obj.opex_fix for obj in cost_objs}
        # installed electrical/thermal capacity: {'pp_chp': 30000,...}
        self.cap_installed = {obj.uid: obj.out_max for obj in cost_objs}
        self.cap_installed = {k: sum(filter(None, v.values()))
                              for k, v in self.cap_installed.items()}

        # why do we need revenues? price=0, so we just leave this code here..
        self.output_revenues = {}
        for obj in revenue_objs:
            if isinstance(obj.outputs[0].price, (float, int)):
                price = [obj.outputs[0].price] * len(self.timesteps)
                self.output_revenues[obj.uid] = price
            else:
                self.output_revenues[obj.uid] = obj.outputs[0].price

        # get dispatch expenditure for renewable energies with dispatch
        self.dispatch_ex = {obj.uid: obj.dispatch_ex
                            for obj in self.dispatch_source_objs}

        # objective function
        def obj_rule(self):
            expr = 0

            # variable opex including resource consumption
            expr += sum(self.w[I[e], e, t] *
                        (self.input_costs[e] + self.opex_var[e])
                        for e in self.cost_uids for t in self.timesteps)

            # fixed opex of components
            expr += sum(self.cap_installed[e] * (self.opex_fix[e])
                        for e in self.cost_uids)

            # revenues from outputs of components
            expr += - sum(self.w[e, O[e], t] * self.output_revenues[e][t]
                          for e in self.revenue_uids for t in self.timesteps)

            # dispatch costs
            if self.dispatch_source_objs:
                expr += sum(self.dispatch[e, t] * self.dispatch_ex[e]
                            for e in self.dispatch_source_uids
                            for t in self.timesteps)

            # add additional capacity & capex for investment models
            if(self.invest is True):
                self.capex = {obj.uid: obj.capex for obj in cost_objs}
                self.crf = {obj.uid: obj.crf for obj in cost_objs}

                expr += sum(self.add_cap[I[e], e] * self.crf[e] *
                            (self.capex[e] + self.opex_fix[e])
                            for e in self.cost_uids)
                expr += sum(self.soc_add[e] * self.crf[e] *
                            (self.capex[e] + self.opex_fix[e])
                            for e in self.simple_storage_uids)

            # artificial costs for excess or shortage
            if self.slack["excess"] is True:
                expr += sum(self.excess_slack[e, t] * 3000
                            for e in self.bus_uids for t in self.timesteps)
            if self.slack["shortage"] is True:
                expr += sum(self.shortage_slack[e, t] * 3000
                            for e in self.bus_uids for t in self.timesteps)
            return(expr)
        self.objective = po.Objective(rule=obj_rule)

    def solve(self, solver='glpk', solver_io='lp', debug=False,
              duals=False, **kwargs):
        """ Method that solves the optimization model

        Parameters
        ----------

        self : pyomo.ConcreteModel
        solver str: solver to be used e.g. 'glpk','gurobi','cplex'
        solver_io str: str that defines the solver interaction
        (file or interface) 'lp','nl','python'
        **kwargs: other arguments for the pyomo.opt.SolverFactory.solve()
        method

        Returns
        -------
        self : solved pyomo.ConcreteModel() instance
        """

        from pyomo.opt import SolverFactory
        # Create a 'dual' suffix component on the instance
        # so the solver plugin will know which suffixes to collect
        if duals is True:
            # dual variables (= shadow prices)
            self.dual = po.Suffix(direction=po.Suffix.IMPORT)
            # reduced costs
            self.rc = po.Suffix(direction=po.Suffix.IMPORT)
        # write lp-file
        if(debug is True):
            self.write('problem.lp',
                       io_options={'symbolic_solver_labels': True})
            # print instance
            # instance.pprint()

        # solve instance
        opt = SolverFactory(solver, solver_io=solver_io)
        # store results
        results = opt.solve(self, **kwargs)

        if (results.solver.status == "ok") and \
           (results.solver.termination_condition == "optimal"):
            # Do something when the solution in optimal and feasible
            self.solutions.load_from(results)

        elif (results.solver.termination_condition == "infeasible"):
            print("Model is infeasible",
                  "Solver Status: ", results.solver.status)
        else:
            # Something else is wrong
            print ("Solver Status: ",  results.solver.status, "\n"
                   "Termination condition: ",
                   results.solver.termination_condition)

    def edges(self, components):
        """Method that creates a list with all edges for the objects in
        components.

        Parameters
        ----------
        self :
        components : list of component objects

        Returns
        -------
        edges : list with tupels that represent the edges
        """

        edges = []
        # create a list of tuples
        # e.g. [('coal', 'pp_coal'), ('pp_coal', 'b_el'),...]
        for c in components:
            for i in c.inputs:
                ei = (i.uid, c.uid)
                edges.append(ei)
            for o in c.outputs:
                ej = (c.uid, o.uid)
                edges.append(ej)
        return(edges)


#def io_sets(components):
#    """Function that gets inputs and outputs for given components.
#
#    Parameters
#    ----------
#    components : list of component objects
#
#    Returns
#    -------
#    (I, O) : lists with tupels that represent the edges
#    """
#    O = {obj.uid: [o.uid for o in obj.outputs[:]] for obj in components}
#    I = {obj.uid: [i.uid for i in obj.inputs[:]] for obj in components}
#    return(I, O)
